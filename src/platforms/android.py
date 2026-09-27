"""Android devices through adb."""
from pathlib import Path
import threading
from typing import List, Optional

from infra.tools import AdbError, resolve_adb_executable
from platforms.base import CollectResult, DeviceInfo, PlatformDriver, parse_device_lines, run_probe, run_transfer


class AndroidDriver(PlatformDriver):
    key = "android"
    label = "Android"
    package_kind = "APK"
    crash_log_description = "Android 崩溃日志"
    tool_error = AdbError

    def detect(self) -> List[DeviceInfo]:
        output = run_probe([resolve_adb_executable(), "devices", "-l"], AdbError, "adb")
        devices = []
        for line in parse_device_lines(output, skip=lambda line: line.startswith("List of devices")):
            parts = line.split()
            if len(parts) < 2 or parts[0].startswith("emulator-"):
                continue
            devices.append(DeviceInfo(device_id=parts[0], platform=self.key, status=parts[1]))
        return devices

    def install_command(self, device_id: str, package: Path, *, allow_test: bool = False,
                        executable: Optional[str] = None) -> List[str]:
        command = [executable or resolve_adb_executable(), "-s", device_id, "install"]
        if allow_test:
            command.append("-t")
        command.append(str(package))
        return command

    def crash_log_destination(self, output_dir: Path) -> Path:
        return output_dir / "crash.log"

    def collect_crash_log(self, device_id: str, output_dir: Path,
                          cancel: Optional[threading.Event] = None) -> CollectResult:
        """Append `dumpsys dropbox --print` to crash.log; nothing is written on failure."""
        log_path = self.crash_log_destination(output_dir)
        command = [resolve_adb_executable(), "-s", device_id, "shell", "dumpsys", "dropbox", "--print"]
        completed = run_transfer(command, cancel)
        if completed.returncode != 0 or not completed.stdout:
            return CollectResult(command=command, process=completed)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="\n") as log_file:
            log_file.write(completed.stdout)
            if not completed.stdout.endswith("\n"):
                log_file.write("\n")
        return CollectResult(command=command, process=completed, appended_to=log_path)


ANDROID = AndroidDriver()
