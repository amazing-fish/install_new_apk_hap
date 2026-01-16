import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class InstallResult:
    command: List[str]
    process: subprocess.CompletedProcess


def install_android(device_id: str, apk_path: Path, allow_test: bool) -> InstallResult:
    command: List[str] = ["adb", "-s", device_id, "install"]
    if allow_test:
        command.append("-t")
    command.append(str(apk_path))
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    return InstallResult(command=command, process=process)


def install_harmony(device_id: str, hap_path: Path) -> InstallResult:
    command = ["hdc", "-t", device_id, "install", str(hap_path)]
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    return InstallResult(command=command, process=process)
