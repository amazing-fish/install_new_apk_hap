import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class InstallHandle:
    command: List[str]
    process: subprocess.Popen[str]


def start_install_android(device_id: str, apk_path: Path, allow_test: bool) -> InstallHandle:
    command: List[str] = ["adb", "-s", device_id, "install"]
    if allow_test:
        command.append("-t")
    command.append(str(apk_path))
    run_kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    process = subprocess.Popen(command, **run_kwargs)
    return InstallHandle(command=command, process=process)


def start_install_harmony(device_id: str, hap_path: Path) -> InstallHandle:
    command = ["hdc", "-t", device_id, "install", str(hap_path)]
    run_kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    process = subprocess.Popen(command, **run_kwargs)
    return InstallHandle(command=command, process=process)
