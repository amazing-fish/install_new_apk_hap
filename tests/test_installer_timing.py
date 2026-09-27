import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from infra import process
from platforms.harmony import HARMONY


def test_install_result_records_elapsed_time(monkeypatch, hdc_executable) -> None:
    def run(command, **kwargs):
        assert kwargs == {"cancel": None}  # installs are stoppable but never time out
        return process.ProcessResult(command, 0, b"installed", b"", 2.345)

    monkeypatch.setattr(process, "run", run)

    command = HARMONY.install_command("harmony-device", Path("Harmony release.hap"))
    result = HARMONY.install(command)

    assert result.command == [
        hdc_executable,
        "-t",
        "harmony-device",
        "install",
        "Harmony release.hap",
    ]
    assert result.process.returncode == 0
    assert result.process.stdout == "installed"
    assert result.duration_seconds == pytest.approx(2.345)


def test_android_install_command_adds_t_only_when_requested(adb_executable) -> None:
    from platforms.android import ANDROID
    apk = Path("app with spaces.apk")
    assert ANDROID.install_command("a", apk, allow_test=True) == [adb_executable, "-s", "a", "install", "-t", str(apk)]
    assert ANDROID.install_command("a", apk) == [adb_executable, "-s", "a", "install", str(apk)]
    assert HARMONY.install_command("h", Path("x.hap"), allow_test=True, executable="hdc") == ["hdc", "-t", "h", "install", "x.hap"]
