import subprocess

import main
from platforms import DeviceInfo
from platforms.base import CollectResult


def test_qiankun_log_runs_as_the_single_cancellable_device_task(app, monkeypatch, deferred_tasks):
    app._apply_device_refresh([DeviceInfo('h', 'harmony', 'device')])
    app.device_tree.selection_set('h')
    app.on_device_select(None)
    calls = []

    def collect(device_id, output_dir, target_key, cancel=None):
        calls.append((device_id, target_key, cancel))
        command = ['hdc', 'file', 'recv']
        return CollectResult(command, subprocess.CompletedProcess(command, -1, '', '命令已中止'))
    monkeypatch.setattr(main.DRIVERS['harmony'], 'collect_app_log', collect)
    shown = []
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: shown.append(args))

    app.fetch_qiankun_log()

    assert app.tasks.current.label == '获取乾崑日志'
    assert app.app_log_button.cget('text') == '获取乾崑日志中…'
    assert app.install_button.cget('text') == '中止获取乾崑日志'
    assert app.install_status_var.get() == '获取乾崑日志中'
    assert app.crash_log_button.instate(['disabled'])
    # The primary button stops the running task; a second task cannot start.
    app.fetch_crash_log()
    assert len(deferred_tasks) == 1
    app.install_to_selected()
    assert app.install_button.cget('text') == '正在中止…'
    deferred_tasks.run_all()

    assert calls[0][:2] == ('h', 'qiankun') and calls[0][2].is_set()
    assert not app.tasks.busy and not shown
    assert app.install_status_var.get() == '已中止'
    assert app.app_log_button.cget('text') == '获取APP日志'
    assert app.install_button.cget('text') == '安装到所选设备'
    assert '获取乾崑日志已中止' in app.log_text.get('1.0', 'end')


def test_demo_log_rejects_android_without_starting_worker(app, monkeypatch):
    app._apply_device_refresh([DeviceInfo('a', 'android', 'device')])
    app.device_tree.selection_set('a')
    app.on_device_select(None)
    warnings = []
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: warnings.append(args))
    started = []
    app.tasks.spawn = started.append

    app.fetch_demo_log()

    assert started == []
    assert not app.tasks.busy
    assert warnings and warnings[-1][1] == '仅支持 Harmony 设备'
    assert '获取Demo日志失败' in app.log_text.get('1.0', 'end')
