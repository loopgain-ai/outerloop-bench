"""Synthetic-only containment tests. No providers or datasets run."""

import importlib
import os
from pathlib import Path
import shlex
import sys
import types
from unittest.mock import Mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sandbox

INTEGRATION = pytest.mark.skipif(
    os.getenv("OUTERLOOP_SANDBOX_INTEGRATION") != "1",
    reason="cached Docker image opt-in",
)


@pytest.fixture(autouse=True)
def reset_cancel():
    sandbox.set_cancel_event(None)
    yield
    sandbox.set_cancel_event(None)


@pytest.fixture
def task_files(tmp_path):
    (tmp_path / "solution.py").write_text("def add(a,b): return a-b")
    (tmp_path / "test_solution.py").write_text(
        "from solution import add\ndef test_add(): assert add(1,2)==3\n"
    )
    (tmp_path / "run_tests.sh").write_text("#!/bin/sh\nexec python3 -m pytest -q\n")
    return tmp_path, ["solution.py", "test_solution.py", "run_tests.sh"]


def test_missing_backend_before_model(monkeypatch, task_files):
    root, names = task_files
    for name in ("oai_worker", "claude_min_worker"):
        module = importlib.import_module(name)
        monkeypatch.setattr(
            module, "api_key", Mock(side_effect=AssertionError("no credentials"))
        )
        monkeypatch.setattr(
            module, "call_api", Mock(side_effect=AssertionError("no models"))
        )
        monkeypatch.setattr(
            sandbox,
            "ensure_available",
            Mock(side_effect=sandbox.SandboxUnavailable("offline")),
        )
        monkeypatch.chdir(root)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                module.__file__,
                "--prompt",
                "synthetic",
                "--task-files",
                *names,
                "--editable-files",
                "solution.py",
            ],
        )
        with pytest.raises(sandbox.SandboxUnavailable):
            module.main()
        module.api_key.assert_not_called()
        module.call_api.assert_not_called()


@pytest.mark.parametrize(
    "name", ["../outside.py", "/outside.py", ".env", ".git", "a/b.py", "a\n.py"]
)
def test_invalid_manifest_before_filesystem(name, tmp_path):
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox.TaskSandbox(tmp_path, [name], [])


def test_input_symlink_rejected(task_files):
    root, names = task_files
    (root / "solution.py").unlink()
    (root / "solution.py").symlink_to(root / "test_solution.py")
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox.TaskSandbox(root, names, ["solution.py"])


@INTEGRATION
def test_both_worker_tools_and_independent_grading(task_files):
    root, names = task_files
    original_test = (root / "test_solution.py").read_text()
    for module_name in ("oai_worker", "claude_min_worker"):
        worker = importlib.import_module(module_name)
        task = sandbox.TaskSandbox(root, names, ["solution.py"])
        assert "failed" in worker.run_tool("bash", {"command": "./run_tests.sh"}, task)
        worker.run_tool(
            "write_file",
            {"path": "solution.py", "content": "def add(a,b): return a+b"},
            task,
        )
        assert "passed" in worker.run_tool("bash", {"command": "./run_tests.sh"}, task)
        worker.run_tool(
            "bash",
            {"command": "printf 'raise RuntimeError()' > test_solution.py"},
            task,
        )
        task.export()
        assert (root / "test_solution.py").read_text() == original_test
        grade = sandbox.TaskSandbox(root, names, [])
        assert "1 passed" in grade.operate("grade", timeout=180)[1]
        (root / "solution.py").write_text("def add(a,b): return a-b")


@INTEGRATION
def test_effective_isolation(task_files, monkeypatch):
    root, names = task_files
    (root / ".env").write_text("HOST_SECRET=synthetic")
    monkeypatch.setenv("HOST_SECRET", "synthetic")
    task = sandbox.TaskSandbox(root, names, ["solution.py"])
    code = "import os,pathlib; assert os.getuid()==65534; assert 'HOST_SECRET' not in os.environ; assert not pathlib.Path('.env').exists(); assert not pathlib.Path('/var/run/docker.sock').exists(); assert len(pathlib.Path('/proc/net/route').read_text().splitlines())==1; assert pathlib.Path('/sys/fs/cgroup/memory.max').read_text().strip()=='134217728'; print('isolated')"
    assert (
        "isolated"
        in task.operate("bash", {"command": "python3 -c " + shlex.quote(code)})[1]
    )


@INTEGRATION
@pytest.mark.parametrize(
    "command",
    [
        "rm solution.py; ln -s /etc/passwd solution.py",
        "rm solution.py; mkfifo solution.py",
        "python3 -c \"open('solution.py','w').write('x'*1100000)\"",
        "python3 -c \"print('x'*70000)\"",
    ],
)
def test_unsafe_exports_or_output_fail_closed(task_files, command):
    root, names = task_files
    original = (root / "solution.py").read_text()
    task = sandbox.TaskSandbox(root, names, ["solution.py"])
    with pytest.raises(sandbox.SandboxUnavailable):
        task.operate("bash", {"command": command})
    assert (root / "solution.py").read_text() == original


@INTEGRATION
def test_deadline_removes_container(task_files):
    root, names = task_files
    task = sandbox.TaskSandbox(root, names, ["solution.py"])
    with pytest.raises(sandbox.SandboxUnavailable):
        task.operate("bash", {"command": "sleep 30"}, timeout=0.3)
    result = sandbox.subprocess.run(
        [
            sandbox._docker(),
            "ps",
            "-aq",
            "--filter",
            "label=outerloop.session=" + sandbox.session_id(),
        ],
        capture_output=True,
        check=True,
        timeout=10,
        env=sandbox._docker_env(),
    )
    assert not result.stdout.strip()
    sandbox.cleanup_session(sandbox.session_id())


def test_missing_image_never_pulls(monkeypatch):
    call = Mock(side_effect=sandbox.subprocess.CalledProcessError(1, "inspect"))
    monkeypatch.setattr(sandbox.subprocess, "run", call)
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox._local_image("docker")
    assert call.call_args.args[0][1:3] == ["image", "inspect"]


@pytest.fixture
def harness(monkeypatch):
    fake = types.ModuleType("loopgain")
    fake.LoopGain = Mock(side_effect=AssertionError("no research loop"))
    monkeypatch.setitem(sys.modules, "loopgain", fake)
    module = importlib.import_module("run_fulltest")
    module._abort.clear()
    sandbox.set_cancel_event(module._abort)
    yield module
    module._abort.clear()


def test_native_cli_never_launches(harness, monkeypatch):
    launch = Mock(side_effect=AssertionError("native process forbidden"))
    monkeypatch.setattr(harness.subprocess, "Popen", launch)
    with pytest.raises(sandbox.SandboxUnavailable):
        harness.run_worker(Path("."), 1, "claude")
    launch.assert_not_called()


def test_fatal_runner_failure_stops_scheduling(harness, monkeypatch):
    run = Mock(side_effect=sandbox.SandboxUnavailable("cleanup unconfirmed"))
    monkeypatch.setattr(harness, "run_trial", run)
    with pytest.raises(sandbox.SandboxUnavailable):
        harness.run_trials([{}, {}, {}], 1)
    run.assert_called_once()
    assert harness._abort.is_set()


@INTEGRATION
def test_background_descendant_removed(task_files):
    root, names = task_files
    task = sandbox.TaskSandbox(root, names, ["solution.py"])
    assert (
        "done"
        in task.operate("bash", {"command": "sleep 30 >/dev/null 2>&1 & echo done"})[1]
    )
    result = sandbox.subprocess.run(
        [
            sandbox._docker(),
            "ps",
            "-aq",
            "--filter",
            "label=outerloop.session=" + sandbox.session_id(),
        ],
        capture_output=True,
        check=True,
        timeout=10,
        env=sandbox._docker_env(),
    )
    assert not result.stdout.strip()


def test_export_envelope_cannot_expand_host_write_set(task_files, monkeypatch):
    import json

    root, names = task_files
    monkeypatch.setattr(sandbox, "ensure_available", lambda: "cached")
    task = sandbox.TaskSandbox(root, names, ["solution.py"])
    original = (root / "solution.py").read_text()
    monkeypatch.setattr(
        sandbox,
        "_run",
        lambda *a: json.dumps(
            {
                "files": {**task.files, "extra.py": "new file"},
                "output": "",
                "returncode": 0,
            }
        ),
    )
    with pytest.raises(sandbox.SandboxUnavailable):
        task.operate("bash", {"command": "unused"})
    assert not (root / "extra.py").exists()
    assert (root / "solution.py").read_text() == original


def test_worker_timeout_always_cleans_session(harness, monkeypatch, task_files):
    root, names = task_files
    monkeypatch.setattr(harness, "ensure_available", lambda: "cached")
    proc = Mock()
    proc.communicate.side_effect = sandbox.subprocess.TimeoutExpired("synthetic", 1200)
    proc.poll.return_value = None
    monkeypatch.setattr(harness.subprocess, "Popen", Mock(return_value=proc))
    cleanup = Mock()
    monkeypatch.setattr(harness, "cleanup_session", cleanup)
    with pytest.raises(sandbox.SandboxUnavailable):
        harness.run_worker(root, 1, "openai", names, ["solution.py"])
    proc.terminate.assert_called()
    cleanup.assert_called_once()
    assert len(cleanup.call_args.args[0]) == 32
    assert harness._abort.is_set()


def test_active_sibling_cancelled_before_more_scheduling(harness, monkeypatch):
    import threading

    entered = threading.Event()
    calls = []

    def trial(item, _stagger):
        calls.append(item)
        if item == 0:
            assert entered.wait(2)
            raise sandbox.SandboxUnavailable("synthetic cleanup failure")
        entered.set()
        assert harness._abort.wait(2)
        sandbox.check_cancelled()

    monkeypatch.setattr(harness, "run_trial", trial)
    with pytest.raises(sandbox.SandboxUnavailable):
        harness.run_trials(list(range(5)), 2)
    assert sorted(calls) == [0, 1]


@INTEGRATION
@pytest.mark.parametrize("module_name", ["oai_worker", "claude_min_worker"])
def test_worker_main_preserves_edit_with_synthetic_provider(
    module_name, task_files, monkeypatch, capsys
):
    root, names = task_files
    module = importlib.import_module(module_name)
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            module.__file__,
            "--prompt",
            "synthetic",
            "--task-files",
            *names,
            "--editable-files",
            "solution.py",
        ],
    )
    monkeypatch.setattr(module, "api_key", lambda: "synthetic-key")
    if module_name == "oai_worker":
        responses = [
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call",
                                    "function": {
                                        "name": "write_file",
                                        "arguments": '{"path":"solution.py","content":"def add(a,b): return a+b"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            {"choices": [{"message": {"content": "done"}}]},
        ]
    else:
        responses = [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call",
                        "name": "write_file",
                        "input": {
                            "path": "solution.py",
                            "content": "def add(a,b): return a+b",
                        },
                    }
                ]
            },
            {"content": [{"type": "text", "text": "done"}]},
        ]
    provider = Mock(side_effect=responses)
    monkeypatch.setattr(module, "call_api", provider)
    module.main()
    assert provider.call_count == 2
    assert (root / "solution.py").read_text() == "def add(a,b): return a+b"
    assert '"num_turns": 2' in capsys.readouterr().out
