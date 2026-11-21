from __future__ import annotations

import sys
import threading
import time

import pytest

from infra import process


def test_buffered_run_captures_stdout_and_stderr():
    res = process.run([sys.executable, "-c", "import sys; print('hello'); print('err', file=sys.stderr)"])
    assert res.returncode == 0
    assert res.stdout.strip() == "hello"
    assert res.stderr.strip() == "err"
    assert not res.interrupted


def test_streaming_run_emits_lines_incrementally():
    seen: list[tuple[str, str]] = []
    timestamps: list[float] = []

    def on_output(stream: str, line: str) -> None:
        seen.append((stream, line))
        timestamps.append(time.perf_counter())

    code = (
        "import sys, time; "
        "print('step-1', flush=True); time.sleep(0.15); "
        "print('warn-1', file=sys.stderr, flush=True); time.sleep(0.15); "
        "print('step-2', flush=True)"
    )
    res = process.run([sys.executable, "-c", code], on_output=on_output)
    assert res.returncode == 0
    assert ("stdout", "step-1") in seen
    assert ("stderr", "warn-1") in seen
    assert ("stdout", "step-2") in seen
    # Verify lines were emitted progressively rather than all at process exit.
    assert timestamps[-1] - timestamps[0] >= 0.15


def test_streaming_run_respects_cancel():
    cancel = threading.Event()
    lines: list[str] = []

    def on_output(_stream: str, line: str) -> None:
        lines.append(line)
        if line == "ready":
            cancel.set()

    code = "import time; print('ready', flush=True); time.sleep(10)"
    started = time.perf_counter()
    res = process.run([sys.executable, "-c", code], cancel=cancel, on_output=on_output)
    elapsed = time.perf_counter() - started
    assert res.cancelled is True
    assert res.returncode != 0
    assert "ready" in lines
    assert elapsed < 3.0


def test_buffered_run_timeout_and_output_limit():
    res_timeout = process.run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)
    assert res_timeout.timed_out is True
    assert res_timeout.returncode != 0

    res_limit = process.run([sys.executable, "-c", "print('A' * 5000)"], output_limit=512)
    assert res_limit.output_exceeded is True
    assert res_limit.returncode != 0


def test_missing_executable_raises_launch_error():
    with pytest.raises(process.ToolLaunchError):
        process.run(["__nonexistent_binary_for_test_12345__"])


def test_streaming_slow_callback_does_not_truncate_output_or_leak_after_return():
    seen: list[str] = []
    callback_done = threading.Event()

    def slow_on_output(_stream: str, line: str) -> None:
        time.sleep(0.25)
        seen.append(line)
        if "Failure [INSTALL_FAILED]" in line:
            callback_done.set()

    code = "print('Performing Streamed Install', flush=True); print('Failure [INSTALL_FAILED]', flush=True)"
    res = process.run([sys.executable, "-c", code], on_output=slow_on_output)
    count_at_return = len(seen)
    time.sleep(0.35)
    assert res.returncode == 0
    assert "Failure [INSTALL_FAILED]" in res.stdout
    assert callback_done.is_set()
    assert len(seen) == count_at_return
    assert seen == ["Performing Streamed Install", "Failure [INSTALL_FAILED]"]


def test_streaming_long_unterminated_line():
    seen: list[str] = []
    code = "import sys; sys.stdout.write('X' * 10000); sys.stdout.flush()"
    res = process.run([sys.executable, "-c", code], on_output=lambda _s, ln: seen.append(ln))
    assert res.returncode == 0
    assert seen == ["X" * 10000]
    assert res.stdout == "X" * 10000
