import os
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import threading
from typing import List, Optional


@dataclass
class InstallResult:
    command: List[str]
    process: subprocess.CompletedProcess


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


def _run_install_command(command: List[str], stop_event: Optional[threading.Event]) -> InstallResult:
    run_kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
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
            return InstallResult(command=command, process=completed)
        try:
            process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            continue
        stdout, stderr = process.communicate()
        completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        return InstallResult(command=command, process=completed)


def run_android_dropbox_dump(device_id: str, log_path: Path) -> CommandResult:
    command = ["adb", "-s", device_id, "shell", "dumpsys", "dropbox", "--print"]
    run_kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    process = subprocess.run(command, **run_kwargs)
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
    return subprocess.run(command, **run_kwargs)


def run_harmony_recent_crash_zip(device_id: str, output_dir: Path, days: int = 7) -> CollectResult:
    remote_crash_dir = "/data/log/faultlog/faultlogger"
    fetch_command = ["hdc", "-t", device_id, "file", "recv", remote_crash_dir, str(output_dir)]
    output_dir.mkdir(parents=True, exist_ok=True)
    fetch_result = _run_command(fetch_command)
    if fetch_result.returncode != 0:
        return CollectResult(command=fetch_command, process=fetch_result)

    local_crash_dir = output_dir / "faultlogger"
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

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = output_dir / f"harmony_crash_{device_id}_{timestamp}.zip"
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
    output_dir.mkdir(parents=True, exist_ok=True)
    find_command = [
        "hdc",
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
            recv_command = ["hdc", "-t", device_id, "file", "recv", remote_dir, str(receive_target)]
            recv_result = _run_command(recv_command)
            if recv_result.returncode != 0:
                continue
            for file_path in receive_target.rglob("*"):
                if file_path.is_file():
                    pulled_files.append(file_path)

        if not pulled_files:
            return CollectResult(
                command=find_command,
                process=subprocess.CompletedProcess(find_command, 0, "", "路径存在但未拉取到文件"),
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = output_dir / f"nextdemo_logs_{device_id}_{timestamp}.zip"
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


def install_android(
    device_id: str,
    apk_path: Path,
    allow_test: bool,
    stop_event: Optional[threading.Event] = None,
) -> InstallResult:
    command: List[str] = ["adb", "-s", device_id, "install"]
    if allow_test:
        command.append("-t")
    command.append(str(apk_path))
    return _run_install_command(command, stop_event)


def install_harmony(
    device_id: str,
    hap_path: Path,
    stop_event: Optional[threading.Event] = None,
) -> InstallResult:
    command = ["hdc", "-t", device_id, "install", str(hap_path)]
    return _run_install_command(command, stop_event)
