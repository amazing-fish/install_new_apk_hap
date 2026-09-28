import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from infra import process
from infra.tools import AdbError
from platforms import harmony
from platforms.android import ANDROID
from platforms.harmony import HARMONY


def test_android_crash_log_reports_unstartable_adb(tmp_path, adb_executable, fake_process) -> None:
    def raise_missing(_command, **_kwargs):
        raise FileNotFoundError("adb")

    fake_process.handler = raise_missing

    result = ANDROID.collect_crash_log("android-device", tmp_path)

    assert result.command[0] == adb_executable
    assert fake_process.calls[0][1]["timeout"] == process.TRANSFER_TIMEOUT
    assert result.process.returncode != 0
    assert "adb" in result.process.stderr
    assert result.appended_to is None
    assert not (tmp_path / "crash.log").exists()


def test_android_crash_log_without_adb_raises(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ADB_EXECUTABLE", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(AdbError, match="未找到 adb"):
        ANDROID.collect_crash_log("android-device", tmp_path)


def test_android_crash_log_appends_output(tmp_path, adb_executable, fake_process) -> None:
    (tmp_path / "crash.log").write_text("earlier\n", encoding="utf-8")
    fake_process.handler = lambda command, **kwargs: (0, "dropbox entry", "")

    result = ANDROID.collect_crash_log("android-device", tmp_path)

    assert fake_process.commands == [[adb_executable, "-s", "android-device", "shell", "dumpsys", "dropbox", "--print"]]
    assert result.appended_to == tmp_path / "crash.log"
    assert (tmp_path / "crash.log").read_text(encoding="utf-8") == "earlier\ndropbox entry\n"


def test_android_crash_log_success_without_output_is_empty_not_written(tmp_path, adb_executable, fake_process) -> None:
    fake_process.handler = lambda command, **kwargs: (0, "", "")

    result = ANDROID.collect_crash_log("android-device", tmp_path)

    assert result.process.returncode == 0
    assert result.appended_to is None and result.zip_path is None
    assert not (tmp_path / "crash.log").exists()


@pytest.mark.parametrize("flags,message", [
    ({"timed_out": True}, "命令超时（超过 120 秒）已终止"),
    ({"cancelled": True}, "命令已中止"),
])
def test_interrupted_log_collection_is_a_failure_with_reason(tmp_path, adb_executable, fake_process, flags, message) -> None:
    fake_process.handler = lambda command, **kwargs: (0, "partial", "", flags)

    result = ANDROID.collect_crash_log("android-device", tmp_path)

    assert result.process.returncode != 0
    assert result.process.stderr == message
    assert not (tmp_path / "crash.log").exists()


def fake_faultlogger_receive(command, cancel=None):
    receive_target = Path(command[-1])
    fresh_dir = receive_target / "faultlogger"
    fresh_dir.mkdir(parents=True, exist_ok=True)
    (fresh_dir / "new_crash.log").write_text("new", encoding="utf-8")
    (fresh_dir / "unrelated.log").write_text("skip", encoding="utf-8")
    return subprocess.CompletedProcess(command, 0, "", "")


def test_harmony_crash_zip_ignores_stale_faultlogger_directory(monkeypatch, tmp_path, hdc_executable) -> None:
    stale_dir = tmp_path / "faultlogger"
    stale_dir.mkdir()
    (stale_dir / "old_crash.log").write_text("old", encoding="utf-8")
    monkeypatch.setattr(harmony, "run_transfer", fake_faultlogger_receive)

    result = HARMONY.collect_crash_log("harmony-device", tmp_path)

    assert result.zip_path is not None and result.file_count == 1
    with zipfile.ZipFile(result.zip_path) as zip_file:
        assert zip_file.namelist() == ["new_crash.log"]


def test_harmony_crash_zip_sanitizes_device_id_in_zip_filename(monkeypatch, tmp_path, hdc_executable) -> None:
    monkeypatch.setattr(harmony, "run_transfer", fake_faultlogger_receive)

    result = HARMONY.collect_crash_log("192.168.0.2:5555", tmp_path)

    assert result.zip_path is not None
    assert ":" not in result.zip_path.name


def test_crash_log_destinations() -> None:
    assert ANDROID.crash_log_destination(Path("D:/")) == Path("D:/") / "crash.log"
    assert HARMONY.crash_log_destination(Path("D:/")) == Path("D:/")
