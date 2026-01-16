import os
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
    run_kwargs = {"capture_output": True, "text": True, "check": False}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    process = subprocess.run(command, **run_kwargs)
    return InstallResult(command=command, process=process)


def install_harmony(device_id: str, hap_path: Path) -> InstallResult:
    command = ["hdc", "-t", device_id, "install", str(hap_path)]
    run_kwargs = {"capture_output": True, "text": True, "check": False}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    process = subprocess.run(command, **run_kwargs)
    return InstallResult(command=command, process=process)
