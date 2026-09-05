"""Fail-closed Docker execution for untrusted candidates (stdlib only).

Images must already exist locally; this module never pulls or builds one.
The image ID is resolved before execution so a mutable tag cannot change mid-run.
"""

from __future__ import annotations

import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024


class SandboxUnavailable(RuntimeError):
    """Infrastructure failure: stop rather than spend on an unexecutable trial."""


class SandboxExecutionError(RuntimeError):
    """Candidate exceeded a limit, crashed, or returned invalid output."""


def _docker() -> str:
    executable = shutil.which("docker")
    if os.name != "posix" or not executable:
        raise SandboxUnavailable(
            "Candidate execution requires Docker on a POSIX host; no host fallback."
        )
    return executable


def _docker_env() -> dict[str, str]:
    # These configure the CLI only; the candidate environment is cleared by env -i.
    return {
        key: os.environ[key]
        for key in ("PATH", "HOME", "DOCKER_CONFIG")
        if key in os.environ
    }


def _local_image(docker: str) -> str:
    image = os.environ.get("OUTERLOOP_SANDBOX_IMAGE", "loopgain-python-pytest:local")
    try:
        result = subprocess.run(
            [docker, "image", "inspect", "--format", "{{.Id}}", image],
            capture_output=True,
            text=True,
            timeout=10,
            env=_docker_env(),
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SandboxUnavailable(
            "Docker or local Python sandbox image unavailable; no automatic pull."
        ) from exc
    image_id = result.stdout.strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise SandboxUnavailable("Docker did not return an immutable local image ID.")
    return image_id


def _command(docker: str, image: str, name: str, directory: Path) -> list[str]:
    return [
        docker,
        "create",
        "--pull=never",
        "--name",
        name,
        "--label",
        "outerloop.session=" + session_id(),
        "--network=none",
        "--read-only",
        "--user=65534:65534",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=32",
        "--memory=128m",
        "--memory-swap=128m",
        "--cpus=1",
        "--ulimit=cpu=20:20",
        "--ulimit=nofile=64:64",
        "--ulimit=core=0:0",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
        "--mount",
        f"type=bind,src={directory},dst=/input,readonly",
        "--workdir=/tmp",
        "--log-driver=none",
        "--entrypoint=/usr/bin/env",
        image,
        "-i",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "HOME=/tmp",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        "python3",
        "-I",
        "-B",
        "-c",
        (
            "import runpy,sys; sys.stdin=open('/input/request.json'); "
            "runpy.run_path('/input/worker.py',run_name='__main__')"
        ),
    ]


def _run(image: str, worker: str, payload: dict, timeout: float) -> str:
    encoded = json.dumps(payload).encode()
    if len(encoded) > MAX_INPUT_BYTES:
        raise SandboxUnavailable("Sandbox input exceeds limit")
    docker = _docker()
    name = f"outerloop-candidate-{uuid.uuid4().hex}"
    with tempfile.TemporaryDirectory(prefix="outerloop-candidate-") as temporary:
        directory = Path(temporary)
        # Only staged worker/request/fixtures are mounted; never repo, home or Docker socket.
        directory.chmod(0o755)
        for filename, contents in (
            ("worker.py", worker.encode()),
            ("request.json", encoded),
        ):
            path = directory / filename
            path.write_bytes(contents)
            path.chmod(0o444)
        runner = directory / "run_tests.sh"
        runner.write_text('#!/bin/sh\nexec python3 -m pytest --tb=short -q "$@"\n')
        runner.chmod(0o555)
        proc = None
        try:
            subprocess.run(
                _command(docker, image, name, directory),
                capture_output=True,
                timeout=15,
                env=_docker_env(),
                check=True,
            )
            proc = subprocess.Popen(
                [docker, "start", "--attach", name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_docker_env(),
                start_new_session=True,
            )
            output = bytearray()
            error = bytearray()
            deadline = time.monotonic() + timeout
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ, output)
                selector.register(proc.stderr, selectors.EVENT_READ, error)
                while selector.get_map():
                    check_cancelled()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise SandboxExecutionError("Sandbox wall-clock timeout")
                    for key, _ in selector.select(min(remaining, 0.1)):
                        chunk = os.read(key.fileobj.fileno(), 4096)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        key.data.extend(chunk)
                        if len(output) + len(error) > MAX_OUTPUT_BYTES:
                            raise SandboxExecutionError("Sandbox output limit exceeded")
            proc.wait(timeout=max(0.01, deadline - time.monotonic()))
            if proc.returncode:
                raise SandboxExecutionError(
                    f"Sandbox worker exited {proc.returncode}: {error[:200]!r}"
                )
            try:
                return output.decode("utf8")
            except UnicodeError as exc:
                raise SandboxExecutionError("Invalid sandbox output encoding") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise SandboxUnavailable("Docker sandbox process failed") from exc
        finally:
            # Remove the container explicitly, including every descendant process.
            # Do not rely on terminating the attached docker CLI to stop a container.
            if proc is not None and proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                cleanup = subprocess.run(
                    [docker, "rm", "--force", name],
                    capture_output=True,
                    timeout=10,
                    env=_docker_env(),
                    check=False,
                )
                if cleanup.returncode and b"No such container" not in cleanup.stderr:
                    raise SandboxUnavailable(
                        "Could not confirm sandbox container cleanup; stop the run."
                    )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise SandboxUnavailable(
                    "Sandbox cleanup unavailable; stop the run."
                ) from exc
            finally:
                if proc is not None:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
                    proc.stdout.close()
                    proc.stderr.close()


def ensure_available() -> str:
    """Exercise the actual isolation flags before any model request is made."""
    check_cancelled()
    image = _local_image(_docker())
    try:
        result = _run(
            image,
            'import pytest,subprocess; subprocess.run(["/bin/sh","-c","true"],check=True); print("sandbox-ready")',
            {},
            15,
        )
    except SandboxExecutionError as exc:
        raise SandboxUnavailable(
            "Sandbox preflight failed; do not start model requests."
        ) from exc
    if result.strip() != "sandbox-ready":
        raise SandboxUnavailable("Unexpected sandbox preflight result")
    return image


_CANCEL_EVENT = None


def set_cancel_event(event):
    global _CANCEL_EVENT
    _CANCEL_EVENT = event


_SESSION = os.environ.get("OUTERLOOP_SANDBOX_SESSION") or uuid.uuid4().hex


def session_id():
    if not re.fullmatch(r"[0-9a-f]{32}", _SESSION):
        raise SandboxUnavailable("Invalid sandbox session")
    return _SESSION


def check_cancelled():
    if _CANCEL_EVENT is not None and _CANCEL_EVENT.is_set():
        raise SandboxUnavailable("Run cancelled")
    flag = os.environ.get("OUTERLOOP_ABORT_FILE")
    if flag and Path(flag).exists():
        raise SandboxUnavailable("Run cancelled after sandbox infrastructure failure")


def install_signal_handlers():
    def stop(_signum, _frame):
        raise SandboxUnavailable("Worker interrupted")

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)


def cleanup_session(session):
    if not re.fullmatch(r"[0-9a-f]{32}", session):
        raise SandboxUnavailable("Invalid cleanup session")
    try:
        result = subprocess.run(
            [_docker(), "ps", "-aq", "--filter", "label=outerloop.session=" + session],
            capture_output=True,
            timeout=10,
            check=True,
            env=_docker_env(),
        )
        ids = result.stdout.decode().split()
        if any(not re.fullmatch(r"[0-9a-f]{12,64}", item) for item in ids):
            raise SandboxUnavailable("Invalid cleanup response")
        if ids:
            subprocess.run(
                [_docker(), "rm", "--force", *ids],
                capture_output=True,
                timeout=10,
                check=True,
                env=_docker_env(),
            )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SandboxUnavailable("Session cleanup unconfirmed") from exc


def validate_files(files):
    if not isinstance(files, dict) or not files or len(files) > 64:
        raise SandboxUnavailable("Invalid task manifest")
    total = 0
    for name, text in files.items():
        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*\.py|run_tests\.sh", name
        ):
            raise SandboxUnavailable("Unsafe task filename")
        if not isinstance(text, str):
            raise SandboxUnavailable("Invalid task text")
        total += len(text.encode())
    if total > 1024 * 1024:
        raise SandboxUnavailable("Task source exceeds 1 MiB")


def read_regular(path):
    import stat

    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
            raise SandboxUnavailable("Task input must be a bounded regular file")
        data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise SandboxUnavailable("Task file exceeds limit")
        return data.decode("utf8")


class TaskSandbox:
    def __init__(self, directory, names, editable):
        self.directory = Path(directory).resolve(strict=True)
        # Validate names before reading any path.
        validate_files({name: "" for name in names})
        self.editable = set(editable)
        if not self.editable <= set(names) or any(
            not name.endswith(".py") or name.startswith("test_")
            for name in self.editable
        ):
            raise SandboxUnavailable("Invalid editable implementation manifest")
        try:
            self.files = {name: read_regular(self.directory / name) for name in names}
        except (OSError, UnicodeError) as exc:
            raise SandboxUnavailable("Unsafe task input") from exc
        validate_files(self.files)
        self.image = ensure_available()

    def preflight(self):
        if ensure_available() != self.image:
            raise SandboxUnavailable("Sandbox image changed during worker session")

    def operate(self, operation, args=None, timeout=90):
        check_cancelled()
        worker = Path(__file__).with_name("container_task.py").read_text()
        try:
            raw = _run(
                self.image,
                worker,
                {
                    "files": self.files,
                    "editable": sorted(self.editable),
                    "operation": operation,
                    "args": args or {},
                },
                timeout,
            )
            result = json.loads(raw)
            files = result["files"]
            validate_files(files)
            if files.keys() != self.files.keys() or not isinstance(
                result["output"], str
            ):
                raise ValueError("Unexpected sandbox response")
            if (
                len(result["output"].encode()) > 65536
                or type(result["returncode"]) is not int
            ):
                raise ValueError("Invalid command result")
            self.files = files
            return result["returncode"], result["output"]
        except (SandboxExecutionError, ValueError, KeyError, TypeError) as exc:
            # Invalid exports are fatal, never reused as host source or retried.
            raise SandboxUnavailable("Sandbox operation or export failed") from exc

    def export(self):
        check_cancelled()
        validate_files(self.files)
        for name in sorted(self.editable):
            # Names were validated; no recursive extraction and no candidate metadata.
            fd, temporary = tempfile.mkstemp(
                prefix=".outerloop-export-", dir=self.directory
            )
            try:
                with os.fdopen(fd, "w") as stream:
                    stream.write(self.files[name])
                os.replace(temporary, self.directory / name)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)


def run_tool(name, args, task):
    if name not in {"bash", "write_file"}:
        return "unknown tool " + str(name)
    _status, output = task.operate(name, args)
    return output[-6000:] if output else "(no output)"
