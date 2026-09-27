import subprocess
from dataclasses import dataclass
from typing import List, Optional, Type

from infra import process
from infra.tools import AdbError, HdcError, ToolError, resolve_adb_executable, resolve_hdc_executable


@dataclass
class DeviceInfo:
    device_id: str
    platform: str
    status: str


@dataclass
class DeviceDetectionResult:
    devices: List[DeviceInfo]
    harmony_error: Optional[str] = None
    android_error: Optional[str] = None


def _is_device_diagnostic_line(line: str) -> bool:
    return line.startswith("*") or line.startswith("[")


def _is_adb_header_line(line: str) -> bool:
    return line.startswith("List of devices")


def _run_probe(command: List[str], error_type: Type[ToolError], tool_name: str) -> str:
    """A probe that cannot run, times out or fails is an error, never 'no devices'."""
    try:
        result = process.run(command, timeout=process.PROBE_TIMEOUT)
    except process.ToolLaunchError as error:
        raise error_type(f'{tool_name} 无法执行：{error}') from error
    command_text = subprocess.list2cmdline(command)
    interruption = process.describe_interruption(result, process.PROBE_TIMEOUT)
    if interruption:
        raise error_type(f'{tool_name} {interruption}：{command_text}')
    failed_output = tool_name == 'HDC' and any(
        line.lstrip().startswith('[Fail]') for line in (result.stdout + '\n' + result.stderr).splitlines()
    )
    if result.returncode != 0 or failed_output:
        raise error_type(
            f'{tool_name} 命令失败（返回码 {result.returncode}）：{command_text}\n'
            f'{result.stdout.strip()}\n{result.stderr.strip()}'
        )
    return result.stdout.strip()


def _run_command(command: List[str]) -> str:
    return _run_probe(command, AdbError, 'adb')


def _run_hdc_command(command: List[str]) -> str:
    return _run_probe(command, HdcError, 'HDC')


def detect_adb_devices() -> List[DeviceInfo]:
    output = _run_command([resolve_adb_executable(), "devices", "-l"])
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
    """Probe both platforms independently; one failing keeps the other's devices."""
    result = DeviceDetectionResult([])
    try:
        result.devices += detect_adb_devices()
    except AdbError as error:
        result.android_error = str(error)
    try:
        result.devices += detect_hdc_devices()
    except HdcError as error:
        result.harmony_error = str(error)
    return result


def get_hdc_device_udid(device_id: str) -> Optional[str]:
    output = _run_hdc_command([resolve_hdc_executable(), "-t", device_id, "shell", "bm", "get", "--udid"])
    if not output:
        return None
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return None
    return lines[-1]
