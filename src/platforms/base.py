"""What every device platform provides, so callers never branch on platform names."""
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import threading
from typing import Dict, List, Optional

from infra import process
from infra.tools import ToolError


@dataclass
class DeviceInfo:
    device_id: str
    platform: str
    status: str


# Some hdc versions, and older adb, exit 0 after printing an explicit failure.
# Markers only ever turn an apparent success into a failure; output text never
# turns a non-zero exit into success.
INSTALL_FAILURE_MARKERS = (
    re.compile(r"^\[Fail\]"),                        # hdc: [Fail][E001000] ... / [Fail]Error ...
    re.compile(r"^error: failed to install", re.I),  # hdc: error: failed to install bundle.
    re.compile(r"^Failure \["),                      # adb: Failure [INSTALL_FAILED_...]
    re.compile(r"^adb: failed to install"),          # adb: failed to install app.apk: ...
)


@dataclass
class InstallResult:
    command: List[str]
    process: subprocess.CompletedProcess
    duration_seconds: float

    @property
    def failure_reason(self) -> Optional[str]:
        """None when the install succeeded; otherwise why it counts as failed."""
        if self.process.returncode != 0:
            return f"返回码 {self.process.returncode}"
        for stream in (self.process.stdout, self.process.stderr):
            for line in (stream or "").splitlines():
                line = line.strip()
                if any(marker.match(line) for marker in INSTALL_FAILURE_MARKERS):
                    return f"输出包含失败标记：{line}"
        return None


@dataclass
class CollectResult:
    """A log collection. Success lands in exactly one of zip_path / appended_to."""
    command: List[str]
    process: subprocess.CompletedProcess
    zip_path: Optional[Path] = None
    file_count: int = 0
    appended_to: Optional[Path] = None


@dataclass(frozen=True)
class AppLogTarget:
    display_name: str
    remote_path: str
    archive_prefix: str


class PlatformDriver:
    key: str = ""
    label: str = ""
    package_kind: str = ""          # "APK" / "HAP": which scanned package this platform installs
    supports_udid: bool = False
    app_log_targets: Dict[str, AppLogTarget] = {}
    crash_log_description: str = "崩溃日志"
    tool_error: type = ToolError

    def detect(self, cancel: Optional[threading.Event] = None) -> List[DeviceInfo]:
        raise NotImplementedError

    def install_command(self, device_id: str, package: Path, *, allow_test: bool = False,
                        executable: Optional[str] = None) -> List[str]:
        raise NotImplementedError

    def install(self, command: List[str], stop_event: Optional[threading.Event] = None) -> InstallResult:
        """Run a command from install_command, so the logged command is the executed one."""
        return run_install(command, stop_event)

    def crash_log_destination(self, output_dir: Path) -> Path:
        """Where collect_crash_log puts its output, for the 'starting' message."""
        return output_dir

    def collect_crash_log(self, device_id: str, output_dir: Path,
                          cancel: Optional[threading.Event] = None) -> CollectResult:
        raise NotImplementedError

    def udid(self, device_id: str, cancel: Optional[threading.Event] = None) -> Optional[str]:
        raise NotImplementedError(f"{self.label} 不支持获取 UDID")

    def collect_app_log(self, device_id: str, output_dir: Path, target_key: str,
                        cancel: Optional[threading.Event] = None) -> CollectResult:
        raise NotImplementedError(f"{self.label} 不支持获取 APP 日志")


def launch_failure(command: List[str], error: OSError) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(command, 1, "", f"命令执行失败: {command[0]} ({error})")


def run_install(command: List[str], stop_event: Optional[threading.Event]) -> InstallResult:
    # Installs can legitimately take minutes; they have no timeout but can be stopped.
    try:
        result = process.run(command, cancel=stop_event)
    except process.ToolLaunchError as error:
        return InstallResult(command, launch_failure(command, error), 0.0)
    return InstallResult(command=command, process=result.completed(), duration_seconds=result.duration_seconds)


def run_transfer(command: List[str], cancel: Optional[threading.Event] = None) -> subprocess.CompletedProcess:
    """Log collection: bounded by TRANSFER_TIMEOUT; any interruption is a failure."""
    try:
        result = process.run(command, timeout=process.TRANSFER_TIMEOUT, cancel=cancel)
    except process.ToolLaunchError as error:
        return launch_failure(command, error)
    interruption = process.describe_interruption(result, process.TRANSFER_TIMEOUT)
    if interruption:
        stderr = "\n".join(part for part in (result.stderr.strip(), interruption) if part)
        return subprocess.CompletedProcess(command, result.returncode or -1, result.stdout, stderr)
    return result.completed()


def run_probe(command: List[str], error_type: type, tool_name: str, *, fail_marker: Optional[str] = None,
              cancel: Optional[threading.Event] = None) -> str:
    """A probe that cannot run, times out, is cancelled or fails is an error, never 'no devices'."""
    try:
        result = process.run(command, timeout=process.PROBE_TIMEOUT, cancel=cancel)
    except process.ToolLaunchError as error:
        raise error_type(f'{tool_name} 无法执行：{error}') from error
    command_text = subprocess.list2cmdline(command)
    interruption = process.describe_interruption(result, process.PROBE_TIMEOUT)
    if interruption:
        raise error_type(f'{tool_name} {interruption}：{command_text}')
    failed_output = fail_marker is not None and any(
        line.lstrip().startswith(fail_marker) for line in (result.stdout + '\n' + result.stderr).splitlines()
    )
    if result.returncode != 0 or failed_output:
        raise error_type(
            f'{tool_name} 命令失败（返回码 {result.returncode}）：{command_text}\n'
            f'{result.stdout.strip()}\n{result.stderr.strip()}'
        )
    return result.stdout.strip()


def safe_filename_part(value: str) -> str:
    safe = "".join(
        char if char.isalnum() or char in ("-", "_", ".") else "_"
        for char in value.strip()
    )
    return safe or "device"


def parse_device_lines(output: str, *, skip=lambda line: False) -> List[str]:
    """Non-empty lines that are not '* daemon ...' / '[Info] ...' style diagnostics."""
    return [
        line for line in (raw.strip() for raw in output.splitlines())
        if line and not line.startswith(("*", "[")) and not skip(line)
    ]
