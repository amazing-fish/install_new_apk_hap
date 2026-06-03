import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional


@dataclass
class DeviceInfo:
    device_id: str
    platform: str
    status: str


def _is_device_diagnostic_line(line: str) -> bool:
    return line.startswith("*") or line.startswith("[")


def _is_adb_header_line(line: str) -> bool:
    return line.startswith("List of devices")


@lru_cache(maxsize=1)
def _resolve_hdc_executable() -> str:
    for env_name in ("HDC_EXECUTABLE", "HDC_PATH"):
        configured_path = os.getenv(env_name)
        if configured_path:
            path = Path(configured_path)
            if path.is_dir():
                return str(path / "hdc.exe")
            return configured_path

    path_hdc = shutil.which("hdc")
    if path_hdc:
        return path_hdc

    candidate_paths = [
        Path(os.getenv("LOCALAPPDATA", "")) / "Huawei" / "Sdk" / "default" / "openharmony" / "toolchains" / "hdc.exe",
        Path(os.getenv("APPDATA", "")) / "Huawei" / "Sdk" / "default" / "openharmony" / "toolchains" / "hdc.exe",
        Path(os.getenv("ProgramFiles", "")) / "Huawei" / "DevEco Studio" / "sdk" / "default" / "openharmony" / "toolchains" / "hdc.exe",
        Path(os.getenv("ProgramFiles(x86)", "")) / "Huawei" / "DevEco Studio" / "sdk" / "default" / "openharmony" / "toolchains" / "hdc.exe",
        Path("D:/Develop/Tool/DevEcoStudio/sdk/default/openharmony/toolchains/hdc.exe"),
    ]
    for candidate in candidate_paths:
        if candidate.exists():
            return str(candidate)

    return "hdc"


def _resolve_command(command: List[str]) -> List[str]:
    if command and command[0] == "hdc":
        return [_resolve_hdc_executable(), *command[1:]]
    return command


def _run_command(command: List[str]) -> str:
    try:
        run_kwargs = {
            "check": False,
            "capture_output": True,
            "text": True,
        }
        if os.name == "nt":
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            _resolve_command(command),
            **run_kwargs,
        )
    except FileNotFoundError:
        return ""
    return result.stdout.strip()


def detect_adb_devices() -> List[DeviceInfo]:
    output = _run_command(["adb", "devices", "-l"])
    devices: List[DeviceInfo] = []
    if not output:
        return devices
    lines = output.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if _is_device_diagnostic_line(line) or _is_adb_header_line(line):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        device_id = parts[0]
        if device_id.startswith("emulator-"):
            continue
        status = parts[1]
        devices.append(DeviceInfo(device_id=device_id, platform="android", status=status))
    return devices


def detect_hdc_devices() -> List[DeviceInfo]:
    output = _run_command(["hdc", "list", "targets"])
    devices: List[DeviceInfo] = []
    if not output:
        return devices
    lines = output.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line == "[Empty]" or _is_device_diagnostic_line(line):
            continue
        parts = line.split()
        if not parts:
            continue
        device_id = parts[0]
        status = parts[1] if len(parts) > 1 else "device"
        devices.append(DeviceInfo(device_id=device_id, platform="harmony", status=status))
    return devices


def detect_devices() -> List[DeviceInfo]:
    return detect_adb_devices() + detect_hdc_devices()


def get_hdc_device_udid(device_id: str) -> Optional[str]:
    run_kwargs = {
        "check": False,
        "capture_output": True,
        "text": True,
    }
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            _resolve_command(["hdc", "-t", device_id, "shell", "bm", "get", "--udid"]),
            **run_kwargs,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    if not output:
        return None
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return None
    return lines[-1]
