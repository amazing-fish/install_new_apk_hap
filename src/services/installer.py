import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import threading
from typing import List, Optional

from infra import process
from infra.tools import resolve_adb_executable, resolve_hdc_executable


# Some hdc versions, and older adb, exit 0 after printing an explicit failure.
# Markers only ever turn an apparent success into a failure; output text never
# turns a non-zero exit into success.
INSTALL_FAILURE_MARKERS = (
    re.compile(r"^\[Fail\]"),                     # hdc: [Fail][E001000] ... / [Fail]Error ...
    re.compile(r"^error: failed to install", re.I),  # hdc: error: failed to install bundle.
    re.compile(r"^Failure \["),                    # adb: Failure [INSTALL_FAILED_...]
    re.compile(r"^adb: failed to install"),         # adb: failed to install app.apk: ...
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
class CommandResult:
    command: List[str]
    process: subprocess.CompletedProcess


@dataclass
class CollectResult:
    command: List[str]
    process: subprocess.CompletedProcess
    zip_path: Optional[Path] = None
    file_count: int = 0


@dataclass(frozen=True)
class HarmonyAppLogTarget:
    display_name: str
    remote_path: str
    archive_prefix: str


HARMONY_APP_LOG_TARGETS = {
    "qiankun": HarmonyAppLogTarget(
        display_name="乾崑日志",
        remote_path="/data/app/el2/100/base/com.yinwang.qiankunapp.hm/haps/phone/files/qklog/",
        archive_prefix="qiankun_logs",
    ),
    "demo": HarmonyAppLogTarget(
        display_name="Demo日志",
        remote_path="/data/app/el2/100/base/adsmobilesdk.all.huawei/haps/entry/files",
        archive_prefix="demo_logs",
    ),
}


def _safe_filename_part(value: str) -> str:
    safe = "".join(
        char if char.isalnum() or char in ("-", "_", ".") else "_"
        for char in value.strip()
    )
    return safe or "device"


def _run_install_command(command: List[str], stop_event: Optional[threading.Event]) -> InstallResult:
    # Installs can legitimately take minutes; they have no timeout but can be stopped.
    try:
        result = process.run(command, cancel=stop_event)
    except process.ToolLaunchError as error:
        return InstallResult(command, _launch_failure(command, error), 0.0)
    return InstallResult(command=command, process=result.completed(), duration_seconds=result.duration_seconds)


def _launch_failure(command: List[str], error: OSError) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(command, 1, "", f"命令执行失败: {command[0]} ({error})")


def run_android_dropbox_dump(
    device_id: str,
    log_path: Path,
    cancel: Optional[threading.Event] = None,
) -> CommandResult:
    command = [resolve_adb_executable(), "-s", device_id, "shell", "dumpsys", "dropbox", "--print"]
    completed = _run_command(command, cancel)
    if completed.returncode == 0 and completed.stdout:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="\n") as log_file:
            log_file.write(completed.stdout)
            if not completed.stdout.endswith("\n"):
                log_file.write("\n")
    return CommandResult(command=command, process=completed)


def _run_command(
    command: List[str],
    cancel: Optional[threading.Event] = None,
) -> subprocess.CompletedProcess:
    """Log collection: bounded by TRANSFER_TIMEOUT; any interruption is a failure."""
    try:
        result = process.run(command, timeout=process.TRANSFER_TIMEOUT, cancel=cancel)
    except process.ToolLaunchError as error:
        return _launch_failure(command, error)
    interruption = process.describe_interruption(result, process.TRANSFER_TIMEOUT)
    if interruption:
        stderr = "\n".join(part for part in (result.stderr.strip(), interruption) if part)
        return subprocess.CompletedProcess(command, result.returncode or -1, result.stdout, stderr)
    return result.completed()


def run_harmony_recent_crash_zip(
    device_id: str,
    output_dir: Path,
    days: int = 7,
    cancel: Optional[threading.Event] = None,
) -> CollectResult:
    hdc = resolve_hdc_executable()
    remote_crash_dir = "/data/log/faultlog/faultlogger"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_device_id = _safe_filename_part(device_id)
    with tempfile.TemporaryDirectory(prefix=f"harmony_crash_{safe_device_id}_", dir=output_dir) as temp_dir:
        receive_dir = Path(temp_dir)
        fetch_command = [hdc, "-t", device_id, "file", "recv", remote_crash_dir, str(receive_dir)]
        fetch_result = _run_command(fetch_command, cancel)
        if fetch_result.returncode != 0:
            return CollectResult(command=fetch_command, process=fetch_result)

        local_crash_dir = receive_dir / "faultlogger"
        if not local_crash_dir.exists():
            return CollectResult(
                command=fetch_command,
                process=subprocess.CompletedProcess(
                    fetch_command,
                    1,
                    "",
                    "未找到拉取后的 faultlogger 目录",
                ),
            )

        cutoff = datetime.now() - timedelta(days=days)
        target_files: List[Path] = []
        for file_path in local_crash_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if "crash" not in file_path.name.lower():
                continue
            modified_at = datetime.fromtimestamp(file_path.stat().st_mtime)
            if modified_at >= cutoff:
                target_files.append(file_path)

        if not target_files:
            return CollectResult(
                command=fetch_command,
                process=subprocess.CompletedProcess(fetch_command, 0, "", "最近 7 天未匹配到 crash 文件"),
                file_count=0,
            )

        zip_path = output_dir / f"harmony_crash_{safe_device_id}_{timestamp}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in target_files:
                arcname = file_path.relative_to(local_crash_dir)
                zip_file.write(file_path, arcname.as_posix())

    return CollectResult(
        command=fetch_command,
        process=fetch_result,
        zip_path=zip_path,
        file_count=len(target_files),
    )


def run_harmony_app_log_zip(
    device_id: str,
    output_dir: Path,
    target_key: str,
    cancel: Optional[threading.Event] = None,
) -> CollectResult:
    """Pull one known Harmony app log directory directly and archive it locally."""
    try:
        target = HARMONY_APP_LOG_TARGETS[target_key]
    except KeyError as error:
        raise ValueError(f"unknown Harmony app log target: {target_key}") from error

    hdc = resolve_hdc_executable()
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_device_id = _safe_filename_part(device_id)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with tempfile.TemporaryDirectory(
        prefix=f"{target.archive_prefix}_{safe_device_id}_",
        dir=output_dir,
    ) as temp_dir:
        temp_base = Path(temp_dir)
        receive_target = temp_base / target_key
        recv_command = [
            hdc,
            "-t",
            device_id,
            "file",
            "recv",
            target.remote_path,
            str(receive_target),
        ]
        recv_result = _run_command(recv_command, cancel)
        if recv_result.returncode != 0:
            return CollectResult(command=recv_command, process=recv_result)

        pulled_files = sorted(path for path in temp_base.rglob("*") if path.is_file())
        if not pulled_files:
            return CollectResult(
                command=recv_command,
                process=subprocess.CompletedProcess(
                    recv_command,
                    0,
                    recv_result.stdout,
                    recv_result.stderr or f"{target.display_name}拉取成功但未发现文件",
                ),
            )

        zip_path = output_dir / f"{target.archive_prefix}_{safe_device_id}_{timestamp}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in pulled_files:
                zip_file.write(file_path, file_path.relative_to(temp_base).as_posix())

    return CollectResult(
        command=recv_command,
        process=recv_result,
        zip_path=zip_path,
        file_count=len(pulled_files),
    )


def run_harmony_nextdemo_log_zip(device_id: str, output_dir: Path) -> CollectResult:
    """Compatibility wrapper for callers that still use the former NEXTdemo name."""
    return run_harmony_app_log_zip(device_id, output_dir, "demo")


def build_android_install_command(
    device_id: str,
    apk_path: Path,
    allow_test: bool,
    adb_executable: Optional[str] = None,
) -> List[str]:
    command: List[str] = [adb_executable or resolve_adb_executable(), "-s", device_id, "install"]
    if allow_test:
        command.append("-t")
    command.append(str(apk_path))
    return command


def install_android(
    device_id: str,
    apk_path: Path,
    allow_test: bool,
    stop_event: Optional[threading.Event] = None,
    adb_executable: Optional[str] = None,
) -> InstallResult:
    return _run_install_command(
        build_android_install_command(device_id, apk_path, allow_test, adb_executable),
        stop_event,
    )


def build_harmony_install_command(
    device_id: str,
    hap_path: Path,
    hdc_executable: Optional[str] = None,
) -> List[str]:
    return [hdc_executable or resolve_hdc_executable(), "-t", device_id, "install", str(hap_path)]


def install_harmony(
    device_id: str,
    hap_path: Path,
    stop_event: Optional[threading.Event] = None,
    hdc_executable: Optional[str] = None,
) -> InstallResult:
    return _run_install_command(
        build_harmony_install_command(device_id, hap_path, hdc_executable),
        stop_event,
    )
