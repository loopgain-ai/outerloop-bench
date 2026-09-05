"""Trusted operation wrapper, executed only inside the disposable container."""

import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import sys
import time

payload = json.load(sys.stdin)
root = Path("/tmp/task")
root.mkdir()
for name, contents in payload["files"].items():
    if name == "run_tests.sh":
        (root / name).symlink_to("/input/run_tests.sh")
    else:
        (root / name).write_text(contents)
os.chdir(root)
operation = payload["operation"]
args = payload["args"]
output = bytearray()
status = 0
if operation == "write_file":
    name = args.get("path")
    contents = args.get("content")
    if name not in payload["editable"] or not isinstance(contents, str):
        raise ValueError("write_file requires a declared implementation file")
    fd = os.open(name, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "w") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("not a regular file")
        stream.write(contents)
    output.extend(("wrote " + name).encode())
else:
    if operation == "grade":
        command = [
            sys.executable,
            "-m",
            "pytest",
            "--tb=no",
            "-q",
            "-p",
            "no:cacheprovider",
        ]
    elif operation == "bash" and isinstance(args.get("command"), str):
        command = ["/bin/sh", "-c", args["command"]]
    else:
        raise ValueError("Invalid operation")
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + (170 if operation == "grade" else 80)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise RuntimeError("command deadline exceeded")
                for key, _ in selector.select(0.1):
                    chunk = os.read(key.fileobj.fileno(), 4096)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    output.extend(chunk)
                    if len(output) > 65536:
                        raise RuntimeError("command output limit exceeded")
        status = proc.wait(timeout=1)
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=2)
        proc.stdout.close()

files = {}
total = 0
for name in payload["files"]:
    if name == "run_tests.sh":
        files[name] = payload["files"][name]
        continue
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
            raise ValueError("invalid export type or size")
        contents = stream.read(1024 * 1024 + 1)
        total += len(contents)
        if total > 1024 * 1024:
            raise ValueError("export too large")
        files[name] = contents.decode("utf8")
print(
    json.dumps(
        {
            "files": files,
            "returncode": status,
            "output": output.decode("utf8", errors="replace"),
        }
    )
)
