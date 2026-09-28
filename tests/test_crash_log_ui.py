"""One crash-log flow for every platform: dispatch by driver, report by result."""
import subprocess
from pathlib import Path

import pytest

import main
from platforms import DeviceInfo
from platforms.base import CollectResult


@pytest.fixture
def dialogs(monkeypatch):
    shown = []
    monkeypatch.setattr(main.messagebox, 'showinfo', lambda *args: shown.append(('info', *args)))
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: shown.append(('warning', *args)))
    return shown


@pytest.mark.parametrize('platform,result_kwargs,dialog,log_text', [
    ('android', {'appended_to': Path('D:/crash.log')}, 'info', '输出已追加到'),
    ('harmony', {'zip_path': Path('D:/harmony_crash.zip'), 'file_count': 3}, 'info', '共 3 个文件'),
    ('android', {}, 'warning', '获取崩溃日志完成但无输出'),
    ('harmony', {'returncode': 5}, 'warning', '返回码 5'),
])
def test_crash_log_uses_driver_and_reports_by_result(app, monkeypatch, dialogs, platform, result_kwargs, dialog, log_text):
    app._apply_device_refresh([DeviceInfo('d', platform, 'device')])
    app.device_tree.selection_set('d')
    app.on_device_select(None)
    driver = main.DRIVERS[platform]
    calls = []
    returncode = result_kwargs.pop('returncode', 0)

    def collect(device_id, output_dir, cancel=None):
        calls.append((device_id, output_dir))
        command = ['tool', device_id]
        return CollectResult(command, subprocess.CompletedProcess(command, returncode, '', 'diag'), **result_kwargs)

    monkeypatch.setattr(driver, 'collect_crash_log', collect)

    app.fetch_crash_log()

    assert calls == [('d', app._get_log_output_dir())]
    assert dialogs[-1][0] == dialog
    log = app.log_text.get('1.0', 'end')
    assert f'开始获取{driver.crash_log_description}' in log
    assert f'{driver.label} d 崩溃日志命令: tool d' in log
    assert log_text in log
    assert not app.tasks.busy
    assert app.crash_log_button.cget('text') == '获取崩溃日志'


def test_udid_is_offered_only_by_capable_drivers(app, monkeypatch, dialogs):
    app._apply_device_refresh([DeviceInfo('a', 'android', 'device')])
    app.device_tree.selection_set('a')
    app.on_device_select(None)
    started = []
    app.tasks.spawn = started.append

    app.fetch_hdc_udid()

    assert not started and not app.tasks.busy
    assert dialogs[-1][:3] == ('warning', '提示', '仅支持 NEXT 设备获取 UDID')
    assert '为 Android，仅支持 NEXT' in app.log_text.get('1.0', 'end')
