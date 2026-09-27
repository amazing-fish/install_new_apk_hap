import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from infra import process
from services import installer


def test_install_result_records_elapsed_time(monkeypatch, hdc_executable) -> None:
    def run(command, **kwargs):
        assert kwargs == {"cancel": None}  # installs are stoppable but never time out
        return process.ProcessResult(command, 0, b"installed", b"", 2.345)

    monkeypatch.setattr(process, "run", run)

    result = installer.install_harmony(
        "harmony-device",
        Path("Harmony release.hap"),
    )

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
