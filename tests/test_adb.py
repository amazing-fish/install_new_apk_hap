"""adb resolution and 'adb missing is an error, not zero devices'."""
import os
import subprocess
from pathlib import Path

import pytest

import main
from infra import process, tools
from platforms import DeviceDetectionResult, DeviceInfo, detect_devices
from platforms.harmony import HARMONY

# The app fixture stubs refresh_devices out; keep the real one for refresh tests.
REAL_REFRESH_DEVICES = main.App.refresh_devices


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
    monkeypatch.setattr(HARMONY, 'detect', lambda: [harmony])
    result = detect_devices()
    assert result.devices == [harmony]
    assert '未找到 adb' in result.android_error
    assert result.harmony_error is None


@pytest.mark.parametrize('outcome,expected', [
    ((1, '', 'cannot connect to daemon'), '返回码 1'),
    ((0, '', '', {'timed_out': True}), '超时'),
])
def test_failed_or_hung_adb_probe_is_an_error(adb_executable, monkeypatch, fake_process, outcome, expected):
    monkeypatch.setattr(HARMONY, 'detect', lambda: [])
    fake_process.handler = lambda command, **kwargs: outcome
    result = detect_devices()
    assert expected in result.android_error
    assert fake_process.calls[0][1]['timeout'] == process.PROBE_TIMEOUT


def test_android_probe_failure_is_logged_and_blocks_auto_select(app, monkeypatch):
    harmony = DeviceInfo('harmony-a', 'harmony', 'device')
    monkeypatch.setattr(main, 'detect_devices', lambda: DeviceDetectionResult([harmony], android_error='未找到 adb'))
    REAL_REFRESH_DEVICES(app)
    log = app.log_text.get('1.0', 'end')
    assert 'Android 设备探测失败：未找到 adb；已保留检测到的 Harmony 1 台' in log
    assert '未检测到设备' not in log
    # The only visible device may not be the only connected one.
    assert app.device_tree.selection() == ()


@pytest.mark.parametrize('selected', [('android-a',), ('harmony-a',), ()])
def test_preinstall_adb_failure_cannot_redirect_android_to_harmony(app, monkeypatch, preflight, install_plans,
                                                                   selected):
    harmony = DeviceInfo('harmony-a', 'harmony', 'device')
    app._apply_device_refresh([DeviceInfo('android-a', 'android', 'device'), harmony])
    app.device_tree.selection_set(selected)
    app.latest_apk, app.latest_hap = Path('app.apk'), Path('app.hap')
    preflight([harmony], android_error='adb unavailable')
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: None)
    app.install_to_selected()
    if selected == ('harmony-a',):
        assert install_plans == [([('harmony-a', Path('app.hap'))], True)]
    else:
        assert not install_plans
        assert app.install_status_var.get() == '安装异常'


def test_android_install_resolves_adb_once_and_logs_that_path(app, preflight, adb_executable, fake_process):
    devices = [DeviceInfo('android-a', 'android', 'device')]
    app._apply_device_refresh(devices)
    app.latest_apk = Path('app with spaces.apk')
    preflight(devices)
    fake_process.handler = lambda command, **kwargs: (0, 'Success', '')
    app.install_to_selected()
    assert fake_process.commands == [[adb_executable, '-s', 'android-a', 'install', '-t', 'app with spaces.apk']]
    assert subprocess.list2cmdline(fake_process.commands[0]) in app.log_text.get('1.0', 'end')
    assert app.install_status_var.get() == '安装完成'
