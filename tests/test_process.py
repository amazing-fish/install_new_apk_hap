"""The single external command runner, exercised with real child processes."""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from infra import process


def python(code):
    return [sys.executable, "-c", code]


def test_captures_stdout_stderr_and_exit_code():
    result = process.run(python("import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"))
    # Decoded like subprocess text=True: CRLF becomes LF.
    assert (result.returncode, result.stdout, result.stderr) == (3, "out\n", "err\n")
    assert not result.interrupted
    completed = result.completed()
    assert (completed.args, completed.returncode, completed.stdout, completed.stderr) == (
        result.command, 3, "out\n", "err\n")


def test_raw_newlines_can_be_kept():
    result = process.run(python("import sys; sys.stdout.buffer.write(b'a\\r\\nb')"), universal_newlines=False)
    assert result.stdout == "a\r\nb"


def test_large_output_cannot_block_the_child():
    # Well beyond any OS pipe buffer; with pipes and wait() this would hang.
    result = process.run(python("import sys; sys.stdout.write('x' * 5_000_000)"), timeout=30)
    assert result.returncode == 0 and len(result.stdout) == 5_000_000


def test_timeout_kills_and_never_reports_success():
    started = time.monotonic()
    result = process.run(python("import time; time.sleep(30)"), timeout=0.3)
    assert result.timed_out and result.returncode != 0
    assert time.monotonic() - started < 10
    assert process.describe_interruption(result, 0.3) == "命令超时（超过 0.3 秒）已终止"


def test_cancel_stops_a_running_command():
    cancel = threading.Event()
    threading.Timer(0.2, cancel.set).start()
    result = process.run(python("import time; time.sleep(30)"), cancel=cancel)
    assert result.cancelled and not result.timed_out
    assert process.describe_interruption(result) == "命令已中止"


def test_cancelled_command_never_reports_success_even_if_child_exits_zero():
    # On POSIX the child traps SIGTERM and exits 0; on Windows terminate() yields 1.
    child = (
        "import signal, sys, time\n"
        "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    result = process.run(python(child), cancel=cancel, timeout=20)
    assert result.cancelled
    assert result.returncode != 0


def test_output_limit_stops_the_command():
    result = process.run(python("import sys\nwhile True: sys.stdout.write('x' * 65536)"), output_limit=100_000, timeout=30)
    assert result.output_exceeded and result.returncode != 0
    assert len(result.stdout_bytes) <= 100_001


def test_merge_stderr_and_strict_decoding_is_lazy():
    result = process.run(
        python("import sys; sys.stdout.buffer.write(b'\\xff'); sys.stderr.write('e'); sys.exit(1)"),
        merge_stderr=True, encoding="utf-8", errors="strict",
    )
    # The exit status is inspectable even though the output is not valid UTF-8.
    assert result.returncode == 1 and result.stderr_bytes == b""
    with pytest.raises(UnicodeDecodeError):
        result.stdout


def test_missing_executable_raises_tool_launch_error(tmp_path):
    with pytest.raises(process.ToolLaunchError) as error:
        process.run([str(tmp_path / "missing-tool.exe"), "arg"])
    assert isinstance(error.value, OSError)
    assert "missing-tool.exe" in str(error.value)


def test_child_has_no_console_and_no_stdin(monkeypatch):
    seen = {}
    real_popen = subprocess.Popen

    def spy(command, **kwargs):
        seen.update(kwargs)
        return real_popen(command, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", spy)
    result = process.run(python("import sys; print(sys.stdin.read() == '')"))
    assert result.stdout.strip() == "True"
    assert seen["stdin"] == subprocess.DEVNULL
    assert "shell" not in seen
    if os.name == "nt":
        assert seen["creationflags"] == subprocess.CREATE_NO_WINDOW
