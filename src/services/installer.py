import os
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import threading
from typing import List, Optional

from services.hdc import resolve_hdc_executable


@dataclass
class InstallResult:
    command: List[str]
    process: subprocess.CompletedProcess
    duration_seconds: float


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


def _command_error_result(command: List[str], error: Exception) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(command, 1, "", f"命令执行失败: {command[0]} ({error})")


def _safe_filename_part(value: str) -> str:
    safe = "".join(
        char if char.isalnum() or char in ("-", "_", ".") else "_"
        for char in value.strip()
    )
    return safe or "device"


def _run_install_command(command: List[str], stop_event: Optional[threading.Event]) -> InstallResult:
    run_kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    started_at = time.perf_counter()
    process = subprocess.Popen(command, **run_kwargs)
    while True:
        if stop_event and stop_event.is_set():
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            return InstallResult(
                command=command,
                process=completed,
                duration_seconds=time.perf_counter() - started_at,
            )
        try:
            process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            continue
        stdout, stderr = process.communicate()
        completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        return InstallResult(
            command=command,
            process=completed,
            duration_seconds=time.perf_counter() - started_at,
        )


def run_android_dropbox_dump(device_id: str, log_path: Path) -> CommandResult:
    command = ["adb", "-s", device_id, "shell", "dumpsys", "dropbox", "--print"]
    process = _run_command(command)
    if process.returncode == 0 and process.stdout:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="\n") as log_file:
            log_file.write(process.stdout)
            if not process.stdout.endswith("\n"):
                log_file.write("\n")
    return CommandResult(command=command, process=process)


def _run_command(command: List[str]) -> subprocess.CompletedProcess:
    run_kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        return subprocess.run(command, **run_kwargs)
    except OSError as error:
        return _command_error_result(command, error)


def run_harmony_recent_crash_zip(device_id: str, output_dir: Path, days: int = 7) -> CollectResult:
    hdc = resolve_hdc_executable()
    remote_crash_dir = "/data/log/faultlog/faultlogger"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_device_id = _safe_filename_part(device_id)
    with tempfile.TemporaryDirectory(prefix=f"harmony_crash_{safe_device_id}_", dir=output_dir) as temp_dir:
        receive_dir = Path(temp_dir)
        fetch_command = [hdc, "-t", device_id, "file", "recv", remote_crash_dir, str(receive_dir)]
        fetch_result = _run_command(fetch_command)
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


def run_harmony_nextdemo_log_zip(device_id: str, output_dir: Path) -> CollectResult:
    hdc = resolve_hdc_executable()
    output_dir.mkdir(parents=True, exist_ok=True)
    find_command = [
        hdc,
        "-t",
        device_id,
        "shell",
        "find",
        "/data/app",
        "-type",
        "d",
        "-path",
        "*/haps/entry/files/log-ads",
    ]
    find_result = _run_command(find_command)
    if find_result.returncode != 0:
        return CollectResult(command=find_command, process=find_result)

    remote_dirs = [line.strip() for line in find_result.stdout.splitlines() if line.strip()]
    if not remote_dirs:
        return CollectResult(
            command=find_command,
            process=subprocess.CompletedProcess(find_command, 0, "", "未找到 haps/entry/files/log-ads 路径"),
        )

    pulled_files: List[Path] = []
    with tempfile.TemporaryDirectory(prefix="nextdemo_") as temp_dir:
        temp_base = Path(temp_dir)
        for index, remote_dir in enumerate(remote_dirs, start=1):
            receive_target = temp_base / f"log_ads_{index}"
            recv_command = [hdc, "-t", device_id, "file", "recv", remote_dir, str(receive_target)]
            recv_result = _run_command(recv_command)
            if recv_result.returncode != 0:
                return CollectResult(command=recv_command, process=recv_result)
            for file_path in receive_target.rglob("*"):
                if file_path.is_file():
                    pulled_files.append(file_path)

        if not pulled_files:
            return CollectResult(
                command=find_command,
                process=subprocess.CompletedProcess(find_command, 0, "", "路径存在但未拉取到文件"),
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = output_dir / f"nextdemo_logs_{_safe_filename_part(device_id)}_{timestamp}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in pulled_files:
                arcname = file_path.relative_to(temp_base)
                zip_file.write(file_path, arcname.as_posix())

    return CollectResult(
        command=find_command,
        process=find_result,
        zip_path=zip_path,
        file_count=len(pulled_files),
    )


def build_android_install_command(
    device_id: str,
    apk_path: Path,
    allow_test: bool,
) -> List[str]:
    command: List[str] = ["adb", "-s", device_id, "install"]
    if allow_test:
        command.append("-t")
    command.append(str(apk_path))
    return command


def install_android(
    device_id: str,
    apk_path: Path,
    allow_test: bool,
    stop_event: Optional[threading.Event] = None,
) -> InstallResult:
    return _run_install_command(
        build_android_install_command(device_id, apk_path, allow_test),
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
