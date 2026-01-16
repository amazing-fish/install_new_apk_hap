import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class DeviceInfo:
    device_id: str
    platform: str
    status: str


def _run_command(command: List[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
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
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        device_id = parts[0]
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
        if line == "[Empty]":
            continue
        device_id = line
        status = "device"
        devices.append(DeviceInfo(device_id=device_id, platform="harmony", status=status))
    return devices


def detect_devices() -> List[DeviceInfo]:
    return detect_adb_devices() + detect_hdc_devices()
