import subprocess
from pathlib import Path
from typing import List


def install_android(device_id: str, apk_path: Path, allow_test: bool) -> subprocess.CompletedProcess:
    command: List[str] = ["adb", "-s", device_id, "install"]
    if allow_test:
        command.append("-t")
    command.append(str(apk_path))
    return subprocess.run(command, capture_output=True, text=True, check=False)


def install_harmony(device_id: str, hap_path: Path) -> subprocess.CompletedProcess:
    command = ["hdc", "-t", device_id, "install", str(hap_path)]
    return subprocess.run(command, capture_output=True, text=True, check=False)
