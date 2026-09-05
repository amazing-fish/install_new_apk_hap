import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from services.hdc import HdcError, resolve_hdc_executable


@dataclass
class DeviceInfo:
    device_id: str
    platform: str
    status: str


@dataclass
class DeviceDetectionResult:
    devices: List[DeviceInfo]
    harmony_error: Optional[str] = None


def _is_device_diagnostic_line(line: str) -> bool:
    return line.startswith("*") or line.startswith("[")


def _is_adb_header_line(line: str) -> bool:
    return line.startswith("List of devices")


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
            command,
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
    output = _run_hdc_command([resolve_hdc_executable(), "list", "targets"])
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
        device_id = line
        status = "device"
        devices.append(DeviceInfo(device_id=device_id, platform="harmony", status=status))
    return devices


def detect_devices() -> DeviceDetectionResult:
    devices = detect_adb_devices()
    try:
        devices += detect_hdc_devices()
    except HdcError as error:
        return DeviceDetectionResult(devices, str(error))
    return DeviceDetectionResult(devices)


def _run_hdc_command(command: List[str]) -> str:
    run_kwargs = {
        "check": False,
        "capture_output": True,
        "text": True,
    }
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            command,
            **run_kwargs,
        )
    except OSError as error:
        raise HdcError(f'HDC 无法执行：{subprocess.list2cmdline(command)} ({error})') from error
    failed_output = any(line.lstrip().startswith('[Fail]') for line in (result.stdout + '\n' + result.stderr).splitlines())
    if result.returncode != 0 or failed_output:
        raise HdcError(
            f'HDC 命令失败（返回码 {result.returncode}）：{subprocess.list2cmdline(command)}\n'
            f'{result.stdout.strip()}\n{result.stderr.strip()}'
        )
    return result.stdout.strip()


def get_hdc_device_udid(device_id: str) -> Optional[str]:
    output = _run_hdc_command([resolve_hdc_executable(), "-t", device_id, "shell", "bm", "get", "--udid"])
    if not output:
        return None
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return None
    return lines[-1]
