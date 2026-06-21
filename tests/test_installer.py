import subprocess
import sys
import zipfile
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services import installer


def test_run_android_dropbox_dump_reports_missing_adb(monkeypatch, tmp_path) -> None:
    def raise_missing(_command, **_kwargs):
        raise FileNotFoundError("adb")

    monkeypatch.setattr(installer.subprocess, "run", raise_missing)
    log_path = tmp_path / "crash.log"

    result = installer.run_android_dropbox_dump("android-device", log_path)

    assert result.command[0] == "adb"
    assert result.process.returncode != 0
    assert "adb" in result.process.stderr
    assert not log_path.exists()


def test_harmony_crash_zip_ignores_stale_faultlogger_directory(monkeypatch, tmp_path) -> None:
    stale_dir = tmp_path / "faultlogger"
    stale_dir.mkdir()
    (stale_dir / "old_crash.log").write_text("old", encoding="utf-8")

    def fake_run(command):
        receive_target = Path(command[-1])
        fresh_dir = receive_target / "faultlogger"
        fresh_dir.mkdir(parents=True, exist_ok=True)
        (fresh_dir / "new_crash.log").write_text("new", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(installer, "_run_command", fake_run)

    result = installer.run_harmony_recent_crash_zip("harmony-device", tmp_path)

    assert result.zip_path is not None
    with zipfile.ZipFile(result.zip_path) as zip_file:
        names = zip_file.namelist()
    assert "new_crash.log" in names
    assert "old_crash.log" not in names


def test_harmony_crash_zip_sanitizes_device_id_in_zip_filename(monkeypatch, tmp_path) -> None:
    def fake_run(command):
        receive_target = Path(command[-1])
        fresh_dir = receive_target / "faultlogger"
        fresh_dir.mkdir(parents=True, exist_ok=True)
        (fresh_dir / "new_crash.log").write_text("new", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(installer, "_run_command", fake_run)

    result = installer.run_harmony_recent_crash_zip("192.168.0.2:5555", tmp_path)

    assert result.zip_path is not None
    assert ":" not in result.zip_path.name
