import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import List, Optional


@dataclass
class InstallResult:
    command: List[str]
    process: subprocess.CompletedProcess


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
