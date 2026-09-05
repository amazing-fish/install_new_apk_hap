import subprocess
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services import installer


class FakeProcess:
    returncode = 0

    def wait(self, timeout):
        return 0

    def communicate(self, timeout=None):
        return "installed", ""


def test_install_result_records_elapsed_time(monkeypatch, hdc_executable) -> None:
    clock = iter([10.0, 12.345])
    monkeypatch.setattr(installer.time, "perf_counter", lambda: next(clock))
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())

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
    assert result.duration_seconds == pytest.approx(2.345)
