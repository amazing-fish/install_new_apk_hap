"""The single entry point for running external tools (adb, hdc, aapt2, restool).

Output goes to temporary files rather than pipes, so a chatty tool can never
block on a full pipe while we poll for timeout, cancellation or output size.
"""
from dataclasses import dataclass
from functools import cached_property
import locale
import os
import subprocess
import tempfile
import threading
import time
from typing import List, Optional, Sequence


PROBE_TIMEOUT = 15.0      # device listing, UDID and other quick queries
TRANSFER_TIMEOUT = 120.0  # file recv / dumpsys style log collection
_POLL_INTERVAL = 0.05


class ToolLaunchError(OSError):
    """The executable could not be started at all (missing, denied, not a program)."""

    def __init__(self, command: Sequence[str], error: OSError) -> None:
        super().__init__(error.errno, f'{subprocess.list2cmdline(list(command))} ({error})')
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
    errors: str = 'replace'
    universal_newlines: bool = True

    def _decode(self, data: bytes) -> str:
        text = data.decode(self.encoding or locale.getpreferredencoding(False), self.errors)
        if self.universal_newlines:  # same translation as subprocess text=True
            text = text.replace('\r\n', '\n').replace('\r', '\n')
        return text

    # Decoded on first access, so callers can check the exit status before a
    # strict decode can fail (metadata tools rely on that ordering).
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
    return subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def _size(file) -> int:
    return os.fstat(file.fileno()).st_size


def _stop(process: subprocess.Popen, graceful: bool) -> None:
    if graceful:
        process.terminate()
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass
    process.kill()
    process.wait()


def run(
    command: Sequence[str],
    *,
    timeout: Optional[float] = None,
    cancel: Optional[threading.Event] = None,
    output_limit: Optional[int] = None,
    merge_stderr: bool = False,
    encoding: Optional[str] = None,
    errors: str = 'replace',
    universal_newlines: bool = True,
) -> ProcessResult:
    """Run one command without a console window, bounded by time, size and cancel.

    Raises ToolLaunchError when the executable cannot start. Every other outcome,
    including timeout, cancellation and oversize output, is a ProcessResult.
    ``encoding=None`` with ``universal_newlines`` decodes like ``text=True``.
    """
    command = [str(part) for part in command]
    started_at = time.perf_counter()
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
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
                    process.wait(timeout=_POLL_INTERVAL)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if cancel is not None and cancel.is_set():
                    cancelled = True
                    _stop(process, graceful=True)
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    timed_out = True
                    _stop(process, graceful=False)
                    break
                if output_limit is not None and _size(stdout_file) + _size(stderr_file) > output_limit:
                    exceeded = True
                    _stop(process, graceful=False)
                    break
        finally:
            if process.poll() is None:
                _stop(process, graceful=False)
        if output_limit is not None and _size(stdout_file) + _size(stderr_file) > output_limit:
            exceeded = True
        read_limit = -1 if output_limit is None else output_limit + 1
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout_bytes = stdout_file.read(read_limit)
        stderr_bytes = stderr_file.read(read_limit)
    returncode = process.returncode
    if (timed_out or cancelled or exceeded) and returncode == 0:
        # A stopped command must never look successful, even if the child
        # handled SIGTERM itself and exited 0 (POSIX).
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


def describe_interruption(result: ProcessResult, timeout: Optional[float] = None) -> Optional[str]:
    if result.timed_out:
        limit = f'{timeout:g} 秒' if timeout is not None else '时限'
        return f'命令超时（超过 {limit}）已终止'
    if result.cancelled:
        return '命令已中止'
    if result.output_exceeded:
        return '命令输出超出上限，已终止'
    return None
