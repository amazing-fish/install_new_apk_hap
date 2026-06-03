import sys
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services import device_detector


def test_detect_adb_devices_ignores_daemon_diagnostic_lines(monkeypatch) -> None:
    output = """List of devices attached

* daemon not running; starting now at tcp:5037
* daemon started successfully
R5CN1234567 device product:example model:Phone device:phone transport_id:1
"""

    monkeypatch.setattr(device_detector, "_run_command", lambda _command: output)

    devices = device_detector.detect_adb_devices()

    assert [device.device_id for device in devices] == ["R5CN1234567"]
    assert devices[0].status == "device"


def test_detect_adb_devices_ignores_header_after_diagnostic_lines(monkeypatch) -> None:
    output = """* daemon not running; starting now at tcp:5037
* daemon started successfully
List of devices attached
R5CN1234567 device product:example model:Phone device:phone transport_id:1
"""

    monkeypatch.setattr(device_detector, "_run_command", lambda _command: output)

    devices = device_detector.detect_adb_devices()

    assert [device.device_id for device in devices] == ["R5CN1234567"]


def test_detect_hdc_devices_ignores_diagnostic_lines(monkeypatch) -> None:
    output = """* daemon not running; starting now
[Fail] failed to connect hdc server
ABCDEF0123456789
"""

    monkeypatch.setattr(device_detector, "_run_command", lambda _command: output)

    devices = device_detector.detect_hdc_devices()

    assert [device.device_id for device in devices] == ["ABCDEF0123456789"]


def test_detect_hdc_devices_preserves_status_column(monkeypatch) -> None:
    output = "5MT0225B05000904\tUnauthorized\n"

    monkeypatch.setattr(device_detector, "_run_command", lambda _command: output)

    devices = device_detector.detect_hdc_devices()

    assert devices == [
        device_detector.DeviceInfo(
            device_id="5MT0225B05000904",
            platform="harmony",
            status="Unauthorized",
        )
    ]


def test_run_command_uses_hdc_executable_override(monkeypatch) -> None:
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(stdout="5MT0225B05000904\n")

    monkeypatch.setenv("HDC_EXECUTABLE", r"D:\SDK\toolchains\hdc.exe")
    monkeypatch.setattr(device_detector.subprocess, "run", fake_run)

    output = device_detector._run_command(["hdc", "list", "targets"])

    assert output == "5MT0225B05000904"
    assert calls[0][:3] == [r"D:\SDK\toolchains\hdc.exe", "list", "targets"]
