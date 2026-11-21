"""Single entry point for executing external tools (adb, hdc, aapt2, restool).

Supports two safe execution modes:
- Buffered mode (default, `on_output=None`): writes stdout/stderr to temporary
  files so chatty tools can never block on a full OS pipe while we poll for
  timeout, cancellation, or output limits.
- Streaming mode (`on_output` callback provided): reads stdout/stderr on
  dedicated daemon reader threads and emits each line immediately for live
  progress feedback (e.g., during APK/HAP installs) while preserving timeout,
  cancellation, and output-limit guarantees.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
import codecs
import locale
import os
import queue
import subprocess
import tempfile
import threading
import time
from typing import Callable, List, Optional, Sequence


PROBE_TIMEOUT = 15.0      # device listing, UDID and other quick queries
TRANSFER_TIMEOUT = 120.0  # file recv / dumpsys style log collection
_POLL_INTERVAL = 0.05

OutputCallback = Callable[[str, str], None]  # (stream_name: 'stdout'|'stderr', line: str)


class ToolLaunchError(OSError):
    """The executable could not be started at all (missing, denied, not a program)."""

    def __init__(self, command: Sequence[str], error: OSError) -> None:
        super().__init__(error.errno, f"{subprocess.list2cmdline(list(command))} ({error})")
        self.command = list(command)
        self.cause = error


@dataclass(frozen=True)
class ProcessResult:
    command: List[str]
    returncode: int
    stdout_bytes: bytes
    stderr_bytes: bytes
    duration_seconds: float
    timed_out: bool = False
    cancelled: bool = False
    output_exceeded: bool = False
    encoding: Optional[str] = None
    errors: str = "replace"
    universal_newlines: bool = True

    def _decode(self, data: bytes) -> str:
        text = data.decode(self.encoding or locale.getpreferredencoding(False), self.errors)
        if self.universal_newlines:
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text

    @cached_property
    def stdout(self) -> str:
        return self._decode(self.stdout_bytes)

    @cached_property
    def stderr(self) -> str:
        return self._decode(self.stderr_bytes)

    @property
    def interrupted(self) -> bool:
        return self.timed_out or self.cancelled or self.output_exceeded

    def completed(self) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(self.command, self.returncode, self.stdout, self.stderr)


def _creationflags() -> int:
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _size(file) -> int:
    return os.fstat(file.fileno()).st_size


def _stop(proc: subprocess.Popen, graceful: bool) -> None:
    if graceful:
        try:
            proc.terminate()
            proc.wait(timeout=5)
            return
        except (subprocess.TimeoutExpired, OSError):
            pass
    try:
        proc.kill()
        proc.wait(timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _run_buffered(
    command: List[str],
    *,
    timeout: Optional[float],
    cancel: Optional[threading.Event],
    output_limit: Optional[int],
    merge_stderr: bool,
    encoding: Optional[str],
    errors: str,
    universal_newlines: bool,
) -> ProcessResult:
    started_at = time.perf_counter()
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=subprocess.STDOUT if merge_stderr else stderr_file,
                creationflags=_creationflags(),
            )
        except OSError as error:
            raise ToolLaunchError(command, error) from error
        deadline = None if timeout is None else time.monotonic() + timeout
        timed_out = cancelled = exceeded = False
        try:
            while True:
                try:
                    proc.wait(timeout=_POLL_INTERVAL)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if cancel is not None and cancel.is_set():
                    cancelled = True
                    _stop(proc, graceful=True)
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    timed_out = True
                    _stop(proc, graceful=False)
                    break
                if output_limit is not None and _size(stdout_file) + _size(stderr_file) > output_limit:
                    exceeded = True
                    _stop(proc, graceful=False)
                    break
        finally:
            if proc.poll() is None:
                _stop(proc, graceful=False)
        if output_limit is not None and _size(stdout_file) + _size(stderr_file) > output_limit:
            exceeded = True
        read_limit = -1 if output_limit is None else output_limit + 1
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout_bytes = stdout_file.read(read_limit)
        stderr_bytes = stderr_file.read(read_limit)
    returncode = proc.returncode if proc.returncode is not None else -1
    if (timed_out or cancelled or exceeded) and returncode == 0:
        returncode = -1
    return ProcessResult(
        command=command,
        returncode=returncode,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        duration_seconds=time.perf_counter() - started_at,
        timed_out=timed_out,
        cancelled=cancelled,
        output_exceeded=exceeded,
        encoding=encoding,
        errors=errors,
        universal_newlines=universal_newlines,
    )


def _run_streaming(
    command: List[str],
    *,
    timeout: Optional[float],
    cancel: Optional[threading.Event],
    output_limit: Optional[int],
    merge_stderr: bool,
    encoding: Optional[str],
    errors: str,
    universal_newlines: bool,
    on_output: OutputCallback,
) -> ProcessResult:
    started_at = time.perf_counter()
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            bufsize=0,
            creationflags=_creationflags(),
        )
    except OSError as error:
        raise ToolLaunchError(command, error) from error

    resolved_encoding = encoding or locale.getpreferredencoding(False)
    stdout_buf = bytearray()
    stderr_buf = bytearray()
    total_lock = threading.Lock()
    total_bytes = 0
    exceeded_event = threading.Event()
    line_queue: "queue.SimpleQueue[Optional[tuple[str, str]]]" = queue.SimpleQueue()
    stop_callbacks = threading.Event()

    def _dispatch_callbacks() -> None:
        while not stop_callbacks.is_set():
            item = line_queue.get()
            if item is None or stop_callbacks.is_set():
                return
            stream_name, line = item
            try:
                on_output(stream_name, line)
            except Exception:
                pass

    dispatcher = threading.Thread(target=_dispatch_callbacks, daemon=True, name="process-output-cb")
    dispatcher.start()

    def _enqueue_lines(stream_name: str, text_chunk: str, pending: List[str]) -> None:
        if not text_chunk:
            return
        normalized = text_chunk.replace("\r\n", "\n").replace("\r", "\n")
        pending.append(normalized)
        if "\n" not in normalized:
            return
        joined = "".join(pending)
        lines = joined.split("\n")
        pending.clear()
        if lines[-1]:
            pending.append(lines[-1])
        for line in lines[:-1]:
            if line.strip():
                line_queue.put((stream_name, line))

    def _reader(stream, stream_name: str, target_buf: bytearray) -> None:
        nonlocal total_bytes
        decoder = codecs.getincrementaldecoder(resolved_encoding)(errors=errors)
        pending: List[str] = []
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                with total_lock:
                    total_bytes += len(chunk)
                    if output_limit is None or len(target_buf) <= output_limit:
                        take = len(chunk) if output_limit is None else max(0, output_limit + 1 - len(target_buf))
                        if take:
                            target_buf.extend(chunk[:take])
                    if output_limit is not None and total_bytes > output_limit:
                        exceeded_event.set()
                        break
                decoded = decoder.decode(chunk, final=False)
                _enqueue_lines(stream_name, decoded, pending)
            tail = decoder.decode(b"", final=True)
            if tail:
                pending.append(tail.replace("\r\n", "\n").replace("\r", "\n"))
            rem = "".join(pending).strip()
            if rem:
                for line in rem.splitlines():
                    if line.strip():
                        line_queue.put((stream_name, line))
        except OSError:
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    threads: List[threading.Thread] = []
    if proc.stdout is not None:
        t_out = threading.Thread(target=_reader, args=(proc.stdout, "stdout", stdout_buf), daemon=True)
        t_out.start()
        threads.append(t_out)
    if proc.stderr is not None and not merge_stderr:
        t_err = threading.Thread(target=_reader, args=(proc.stderr, "stderr", stderr_buf), daemon=True)
        t_err.start()
        threads.append(t_err)

    deadline = None if timeout is None else time.monotonic() + timeout
    timed_out = cancelled = exceeded = False
    capture_incomplete = False
    try:
        while True:
            try:
                proc.wait(timeout=_POLL_INTERVAL)
                break
            except subprocess.TimeoutExpired:
                pass
            if cancel is not None and cancel.is_set():
                cancelled = True
                _stop(proc, graceful=True)
                break
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                _stop(proc, graceful=False)
                break
            if exceeded_event.is_set():
                exceeded = True
                _stop(proc, graceful=False)
                break
    finally:
        if proc.poll() is None:
            _stop(proc, graceful=False)
        interrupted_flag = timed_out or cancelled or exceeded
        join_timeout = 2.0 if interrupted_flag else 5.0
        for thread in threads:
            thread.join(timeout=join_timeout)
        if any(thread.is_alive() for thread in threads):
            capture_incomplete = True
            for s in (proc.stdout, proc.stderr):
                if s is not None:
                    try:
                        s.close()
                    except OSError:
                        pass
            for thread in threads:
                thread.join(timeout=1.0)
        if interrupted_flag or capture_incomplete:
            stop_callbacks.set()
            line_queue.put(None)
            dispatcher.join(timeout=2.0)
        else:
            line_queue.put(None)
            dispatcher.join()

    if exceeded_event.is_set():
        exceeded = True
    returncode = proc.returncode if proc.returncode is not None else -1
    if (timed_out or cancelled or exceeded or capture_incomplete) and returncode == 0:
        returncode = -1
    return ProcessResult(
        command=command,
        returncode=returncode,
        stdout_bytes=bytes(stdout_buf),
        stderr_bytes=bytes(stderr_buf),
        duration_seconds=time.perf_counter() - started_at,
        timed_out=timed_out,
        cancelled=cancelled,
        output_exceeded=exceeded,
        encoding=encoding,
        errors=errors,
        universal_newlines=universal_newlines,
    )


def run(
    command: Sequence[str],
    *,
    timeout: Optional[float] = None,
    cancel: Optional[threading.Event] = None,
    output_limit: Optional[int] = None,
    merge_stderr: bool = False,
    encoding: Optional[str] = None,
    errors: str = "replace",
    universal_newlines: bool = True,
    on_output: Optional[OutputCallback] = None,
) -> ProcessResult:
    """Run one external command without a console window, bounded by time/size/cancel."""
    cmd_list = [str(part) for part in command]
    if on_output is not None:
        return _run_streaming(
            cmd_list,
            timeout=timeout,
            cancel=cancel,
            output_limit=output_limit,
            merge_stderr=merge_stderr,
            encoding=encoding,
            errors=errors,
            universal_newlines=universal_newlines,
            on_output=on_output,
        )
    return _run_buffered(
        cmd_list,
        timeout=timeout,
        cancel=cancel,
        output_limit=output_limit,
        merge_stderr=merge_stderr,
        encoding=encoding,
        errors=errors,
        universal_newlines=universal_newlines,
    )


def describe_interruption(result: ProcessResult, timeout: Optional[float] = None) -> Optional[str]:
    if result.timed_out:
        limit = f"{timeout:g} 秒" if timeout is not None else "时限"
        return f"命令超时（超过 {limit}）已终止"
    if result.cancelled:
        return "命令已中止"
    if result.output_exceeded:
        return "命令输出超出上限，已终止"
    return None
