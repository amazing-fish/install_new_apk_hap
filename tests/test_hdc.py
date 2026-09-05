import os
import subprocess
import threading
from pathlib import Path

import pytest

import main
from services import device_detector, hdc, installer
from services.device_detector import DeviceDetectionResult, DeviceInfo


@pytest.fixture
def isolated_hdc(monkeypatch, tmp_path):
    for key in ('HDC_EXECUTABLE', 'HDC_PATH', 'DEVECO_SDK_HOME', 'LOCALAPPDATA', 'APPDATA', 'ProgramFiles', 'ProgramFiles(x86)'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('PATH', str(tmp_path / 'empty-path'))


def tool_at(root):
    path = root / ('hdc.exe' if os.name == 'nt' else 'hdc')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    path.chmod(0o755)
    return path.resolve()


@pytest.mark.parametrize('source', ['HDC_EXECUTABLE', 'HDC_PATH', 'DEVECO_SDK_HOME', 'PATH'])
def test_resolves_supported_sources_with_spaces(isolated_hdc, monkeypatch, tmp_path, source):
    root = tmp_path / 'SDK with spaces'
    tool = tool_at(root / 'default/openharmony/toolchains' if source == 'DEVECO_SDK_HOME' else root)
    monkeypatch.setenv(source, str(tool if source == 'HDC_EXECUTABLE' else root))
    assert hdc.resolve_hdc_executable() == str(tool)


def test_priority_and_invalid_explicit_path_do_not_fall_back(isolated_hdc, monkeypatch, tmp_path):
    explicit = tool_at(tmp_path / 'explicit')
    directory = tool_at(tmp_path / 'directory')
    sdk = tool_at(tmp_path / 'sdk/toolchains')
    path = tool_at(tmp_path / 'path')
    monkeypatch.setenv('HDC_EXECUTABLE', str(explicit))
    monkeypatch.setenv('HDC_PATH', str(directory.parent))
    monkeypatch.setenv('DEVECO_SDK_HOME', str(tmp_path / 'sdk'))
    monkeypatch.setenv('PATH', str(path.parent))
    assert hdc.resolve_hdc_executable() == str(explicit)
    explicit.unlink()
    with pytest.raises(hdc.HdcError, match='HDC_EXECUTABLE'):
        hdc.resolve_hdc_executable()
    monkeypatch.delenv('HDC_EXECUTABLE')
    assert hdc.resolve_hdc_executable() == str(directory)
    monkeypatch.delenv('HDC_PATH')
    assert hdc.resolve_hdc_executable() == str(sdk)
    sdk.unlink()
    with pytest.raises(hdc.HdcError, match='DEVECO_SDK_HOME'):
        hdc.resolve_hdc_executable()
    monkeypatch.delenv('DEVECO_SDK_HOME')
    assert hdc.resolve_hdc_executable() == str(path)


@pytest.mark.skipif(os.name != 'nt', reason='Windows installation layout')
def test_deveco_default_installation_without_path(isolated_hdc, monkeypatch, tmp_path):
    tool = tool_at(tmp_path / 'Program Files/Huawei/DevEco Studio/sdk/default/openharmony/toolchains')
    monkeypatch.setenv('ProgramFiles', str(tmp_path / 'Program Files'))
    assert hdc.resolve_hdc_executable() == str(tool)


@pytest.mark.parametrize('relative', ['openharmony/toolchains', 'toolchains'])
def test_sdk_root_layouts(isolated_hdc, monkeypatch, tmp_path, relative):
    tool = tool_at(tmp_path / relative)
    monkeypatch.setenv('DEVECO_SDK_HOME', str(tmp_path))
    assert hdc.resolve_hdc_executable() == str(tool)


def test_missing_hdc_preserves_android_and_reports_failure(isolated_hdc, monkeypatch):
    android = DeviceInfo('android-a', 'android', 'device')
    monkeypatch.setattr(device_detector, 'detect_adb_devices', lambda: [android])
    result = device_detector.detect_devices()
    assert result.devices == [android]
    assert '未找到 HDC' in result.harmony_error


@pytest.mark.parametrize('code,stdout,stderr', [(7, 'server output', 'server failed'), (0, '[Fail] server unavailable', '')])
def test_failed_detection_keeps_diagnostics(monkeypatch, hdc_executable, code, stdout, stderr):
    monkeypatch.setattr(device_detector, 'detect_adb_devices', lambda: [])
    monkeypatch.setattr(subprocess, 'run', lambda command, **kwargs: subprocess.CompletedProcess(command, code, stdout, stderr))
    result = device_detector.detect_devices()
    assert result.devices == []
    assert f'返回码 {code}' in result.harmony_error
    assert stdout in result.harmony_error and stderr in result.harmony_error
    assert hdc_executable in result.harmony_error


def test_empty_hdc_result_is_success(monkeypatch, hdc_executable):
    monkeypatch.setattr(device_detector, 'detect_adb_devices', lambda: [])
    monkeypatch.setattr(subprocess, 'run', lambda command, **kwargs: subprocess.CompletedProcess(command, 0, '[Empty]', ''))
    assert device_detector.detect_devices() == DeviceDetectionResult([])


def test_hdc_permission_failure_is_not_no_devices(monkeypatch, hdc_executable):
    def denied(*args, **kwargs):
        raise PermissionError('permission denied')
    monkeypatch.setattr(subprocess, 'run', denied)
    with pytest.raises(hdc.HdcError, match='permission denied'):
        device_detector.get_hdc_device_udid('device')


@pytest.mark.parametrize('source', ['HDC_EXECUTABLE', 'HDC_PATH', 'DEVECO_SDK_HOME'])
def test_all_operations_use_same_executable_without_path(isolated_hdc, monkeypatch, tmp_path, source):
    root = tmp_path / 'SDK with spaces'
    executable = tool_at(root / 'toolchains' if source == 'DEVECO_SDK_HOME' else root)
    monkeypatch.setenv(source, str(executable if source == 'HDC_EXECUTABLE' else root))
    monkeypatch.setattr(installer.tempfile, 'tempdir', str(tmp_path))
    seen = []

    def record(command, **kwargs):
        seen.append(command)
        assert command[0] == str(executable)
        assert not kwargs.get('shell', False)
        if os.name == 'nt':
            assert kwargs['creationflags'] == subprocess.CREATE_NO_WINDOW
        if command[1:] == ['list', 'targets']:
            output = 'Harmony-01'
        elif command[-1] == '--udid':
            output = 'udid-value'
        elif 'find' in command:
            output = '/data/app/test/haps/entry/files/log-ads'
            # The recv phase must keep the same resolved path.
            monkeypatch.setenv('HDC_EXECUTABLE', str(tmp_path / 'now-invalid.exe'))
        elif 'recv' in command:
            target = Path(command[-1])
            target = target / 'faultlogger' if command[-2].endswith('faultlogger') else target
            target.mkdir(parents=True, exist_ok=True)
            (target / 'current_crash.log').write_text('log', encoding='utf-8')
            output = ''
        else:
            output = 'installed'
        return subprocess.CompletedProcess(command, 0, output, '')

    class Process:
        returncode = 0
        def __init__(self, command, **kwargs):
            record(command, **kwargs)
        def wait(self, timeout):
            return 0
        def communicate(self, timeout=None):
            return 'installed', ''

    monkeypatch.setattr(subprocess, 'run', record)
    monkeypatch.setattr(subprocess, 'Popen', Process)
    assert device_detector.detect_hdc_devices()[0].device_id == 'Harmony-01'
    assert device_detector.get_hdc_device_udid('Harmony-01') == 'udid-value'
    assert installer.install_harmony('Harmony-01', tmp_path / 'app with spaces.hap').process.returncode == 0
    assert installer.run_harmony_recent_crash_zip('Harmony-01', tmp_path / 'crash').file_count == 1
    assert installer.run_harmony_nextdemo_log_zip('Harmony-01', tmp_path / 'next').file_count == 1
    assert len(seen) == 6


def test_nextdemo_receive_failure_retains_return_code(monkeypatch, tmp_path, hdc_executable):
    monkeypatch.setattr(installer.tempfile, 'tempdir', str(tmp_path))
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, '/remote/log-ads', '') if 'find' in command else subprocess.CompletedProcess(command, 23, 'partial output', 'transfer failed')
    monkeypatch.setattr(subprocess, 'run', run)
    result = installer.run_harmony_nextdemo_log_zip('harmony', tmp_path)
    assert result.process.returncode == 23
    assert result.process.stderr == 'transfer failed'
    assert result.zip_path is None


def test_harmony_install_keeps_resolved_path_and_can_stop(monkeypatch, hdc_executable):
    command = installer.build_harmony_install_command('harmony', Path('app.hap'))
    monkeypatch.setenv('HDC_EXECUTABLE', 'invalid-after-command-was-logged.exe')
    calls = []
    class Process:
        returncode = -15
        def terminate(self):
            calls.append('terminate')
        def communicate(self, timeout=None):
            return '', 'stopped'
    def start(actual, **kwargs):
        assert actual == command
        return Process()
    monkeypatch.setattr(subprocess, 'Popen', start)
    stop = threading.Event()
    stop.set()
    result = installer.install_harmony('harmony', Path('app.hap'), stop, hdc_executable=command[0])
    assert calls == ['terminate']
    assert result.process.returncode == -15


def test_refresh_diagnostic_and_recovery_are_visible(app, monkeypatch):
    android = DeviceInfo('android-a', 'android', 'device')
    monkeypatch.setattr(main, 'detect_devices', lambda: DeviceDetectionResult([android], '未找到 HDC'))
    app.after = lambda delay, callback, *args: callback(*args)
    app._refresh_devices_worker(app._latest_refresh_request_id)
    assert app.devices == [android]
    assert 'Harmony 设备探测失败' in app.log_text.get('1.0', 'end')
    assert '未检测到设备' not in app.log_text.get('1.0', 'end')
    monkeypatch.setattr(main, 'detect_devices', lambda: DeviceDetectionResult([android]))
    app._refresh_devices_worker(app._latest_refresh_request_id)
    recovered = app.log_text.get('1.0', 'end')
    assert '设备列表已刷新' in recovered
    app._refresh_devices_worker(app._latest_refresh_request_id)
    assert app.log_text.get('1.0', 'end') == recovered


def test_partial_refresh_does_not_replace_harmony_selection(app):
    android = DeviceInfo('android-a', 'android', 'device')
    app._apply_device_refresh([android, DeviceInfo('harmony-a', 'harmony', 'device')])
    app.device_tree.selection_set('harmony-a')
    app._apply_device_refresh([android], harmony_error='HDC unavailable')
    assert app.device_tree.selection() == ()
    app.device_tree.selection_set('android-a')
    app._apply_device_refresh([android], harmony_error='HDC unavailable')
    assert app.device_tree.selection() == ('android-a',)


@pytest.mark.parametrize('detected_ids', [['android-b'], []])
def test_partial_preinstall_does_not_replace_disconnected_android(app, monkeypatch, detected_ids):
    app._apply_device_refresh([DeviceInfo('android-a', 'android', 'device'), DeviceInfo('harmony-a', 'harmony', 'device')])
    detected = [DeviceInfo(device_id, 'android', 'device') for device_id in detected_ids]
    monkeypatch.setattr(main, 'detect_devices', lambda: DeviceDetectionResult(detected, 'HDC unavailable'))
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: None)
    started = []
    monkeypatch.setattr(main.threading, 'Thread', lambda **kwargs: started.append(kwargs))
    app.after = lambda delay, callback, *args: callback(*args)
    app._prepare_install_worker({'android-a'}, Path('app.apk'), Path('app.hap'), False)
    assert not started
    assert app.device_tree.selection() == ()
    assert not app.installing


@pytest.mark.parametrize('selected', [{'harmony-a'}, {'android-a'}, set()])
def test_preinstall_hdc_failure_cannot_redirect_harmony_to_android(app, monkeypatch, selected):
    android = DeviceInfo('android-a', 'android', 'device')
    app._apply_device_refresh([android, DeviceInfo('harmony-a', 'harmony', 'device')])
    monkeypatch.setattr(main, 'detect_devices', lambda: DeviceDetectionResult([android], 'HDC unavailable'))
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: None)
    started = []
    class Thread:
        def __init__(self, *, target, args, daemon):
            started.append(args)
        def start(self):
            pass
    monkeypatch.setattr(main.threading, 'Thread', Thread)
    app.after = lambda delay, callback, *args: callback(*args)
    app._prepare_install_worker(selected, Path('app.apk'), Path('app.hap'), False)
    if selected != {'android-a'}:
        assert not started
        assert app.install_status_var.get() == '安装异常'
    else:
        assert started[0][0] == ['android-a']
        assert '安装前设备校验完成（耗时 ' in app.log_text.get('1.0', 'end')
        assert 'Harmony 设备探测失败' in app.log_text.get('1.0', 'end')
