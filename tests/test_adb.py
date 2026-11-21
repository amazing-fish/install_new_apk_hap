"""adb resolution and 'adb missing is an error, not zero devices'."""
import os
import subprocess
from pathlib import Path

import pytest

from infra import process, tools
from platforms import DeviceDetectionResult, DeviceInfo, detect_devices
from platforms.harmony import HARMONY


@pytest.fixture
def isolated_adb(monkeypatch, tmp_path):
    for key in ('ADB_EXECUTABLE', 'ANDROID_SDK_ROOT', 'ANDROID_HOME', 'LOCALAPPDATA'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('PATH', str(tmp_path / 'empty-path'))


def adb_at(directory: Path) -> Path:
    path = directory / ('adb.exe' if os.name == 'nt' else 'adb')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    path.chmod(0o755)
    return path.resolve()


def test_resolution_order_explicit_then_path_then_sdk(isolated_adb, monkeypatch, tmp_path):
    explicit = adb_at(tmp_path / 'explicit dir')
    on_path = adb_at(tmp_path / 'path')
    sdk = adb_at(tmp_path / 'sdk/platform-tools')
    monkeypatch.setenv('ADB_EXECUTABLE', f'"{explicit}"')
    monkeypatch.setenv('PATH', str(on_path.parent))
    monkeypatch.setenv('ANDROID_HOME', str(tmp_path / 'sdk'))
    assert tools.resolve_adb_executable() == str(explicit)
    monkeypatch.delenv('ADB_EXECUTABLE')
    assert tools.resolve_adb_executable() == str(on_path)
    monkeypatch.setenv('PATH', str(tmp_path / 'empty-path'))
    assert tools.resolve_adb_executable() == str(sdk)


def test_invalid_explicit_adb_does_not_fall_back(isolated_adb, monkeypatch, tmp_path):
    on_path = adb_at(tmp_path / 'path')
    monkeypatch.setenv('PATH', str(on_path.parent))
    monkeypatch.setenv('ADB_EXECUTABLE', str(tmp_path / 'missing' / 'adb.exe'))
    with pytest.raises(tools.AdbError, match='ADB_EXECUTABLE'):
        tools.resolve_adb_executable()


def test_unusable_sdk_root_is_skipped_not_fatal(isolated_adb, monkeypatch, tmp_path):
    monkeypatch.setenv('ANDROID_SDK_ROOT', str(tmp_path / 'not-an-sdk'))
    sdk = adb_at(tmp_path / 'real-sdk/platform-tools')
    monkeypatch.setenv('ANDROID_HOME', str(tmp_path / 'real-sdk'))
    assert tools.resolve_adb_executable() == str(sdk)


def test_missing_adb_is_reported_and_harmony_devices_are_kept(isolated_adb, monkeypatch):
    harmony = DeviceInfo('harmony-a', 'harmony', 'device')
    monkeypatch.setattr(HARMONY, 'detect', lambda cancel=None: [harmony])
    result = detect_devices()
    assert result.devices == [harmony]
    assert '未找到 adb' in result.android_error
    assert result.harmony_error is None


@pytest.mark.parametrize('outcome,expected', [
    ((1, '', 'cannot connect to daemon'), '返回码 1'),
    ((0, '', '', {'timed_out': True}), '超时'),
])
def test_failed_or_hung_adb_probe_is_an_error(adb_executable, monkeypatch, fake_process, outcome, expected):
    monkeypatch.setattr(HARMONY, 'detect', lambda cancel=None: [])
    fake_process.handler = lambda command, **kwargs: outcome
    result = detect_devices()
    assert expected in result.android_error
    assert fake_process.calls[0][1]['timeout'] == process.PROBE_TIMEOUT


