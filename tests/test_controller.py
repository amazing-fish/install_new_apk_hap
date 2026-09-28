"""Tk-free task scheduling and single-device rules."""
import subprocess
import threading
import time
from pathlib import Path

import pytest

import main
from controller import Inbox, InstallOutcome, TaskRunner, build_install_plan, resolve_target, run_install_plan
from infra.tools import HdcError
from platforms import DeviceDetectionResult, DeviceInfo
from platforms.base import CollectResult, InstallResult

# The app fixture stubs refresh_devices out; keep the real one for refresh tests.
REAL_REFRESH_DEVICES = main.App.refresh_devices
ANDROID = DeviceInfo('a', 'android', 'device')
HARMONY = DeviceInfo('h', 'harmony', 'device')


class Steps(list):
    def run_all(self):
        while self:
            self.pop(0)()


@pytest.fixture
def runner():
    steps = Steps()
    changes = []
    tasks = TaskRunner(post=lambda callback: callback(), spawn=steps.append,
                       on_change=lambda: changes.append(tasks.current))
    tasks.steps, tasks.changes = steps, changes
    return tasks


def test_one_task_at_a_time_and_slot_released_after_delivery(runner):
    task = runner.start('crash_log', '崩溃日志')
    assert task.label == '获取崩溃日志' and runner.busy
    assert runner.start('udid', 'UDID') is None
    results = []
    runner.run(task, lambda: 'zip', results.append, results.append)
    assert runner.busy  # still running in the background
    runner.steps.run_all()
    assert results == ['zip'] and not runner.busy
    assert runner.changes == [task, None]


def test_chained_steps_keep_the_slot_until_the_last_one(runner):
    task = runner.start('install', '安装', verb='')
    seen = []

    def first_done(value):
        seen.append(value)
        runner.run(task, lambda: 'installed', seen.append, seen.append)

    runner.run(task, lambda: 'checked', first_done, seen.append)
    runner.steps.pop(0)()
    assert seen == ['checked'] and runner.current is task
    runner.steps.run_all()
    assert seen == ['checked', 'installed'] and not runner.busy


def test_worker_exception_reaches_on_error_and_frees_the_slot(runner):
    task = runner.start('udid', 'UDID')
    errors = []

    def boom():
        raise ValueError('probe failed')

    runner.run(task, boom, lambda _result: None, errors.append)
    runner.steps.run_all()
    assert [str(error) for error in errors] == ['probe failed'] and not runner.busy


def test_callback_exception_still_frees_the_slot(runner):
    task = runner.start('udid', 'UDID')

    def broken_callback(_result):
        raise RuntimeError('bug in callback')

    runner.run(task, lambda: None, broken_callback, broken_callback)
    with pytest.raises(RuntimeError):
        runner.steps.run_all()
    assert not runner.busy


def test_cancel_sets_the_event_once(runner):
    assert runner.cancel() is False
    task = runner.start('crash_log', '崩溃日志')
    assert runner.cancel() is True and task.cancelled
    assert runner.cancel() is False


def test_background_work_does_not_take_the_slot(runner):
    results = []
    runner.background(lambda: 'devices', results.append, results.append)
    assert not runner.busy and runner.start('udid', 'UDID') is not None
    runner.steps.run_all()
    assert results == ['devices']


def test_inbox_runs_posts_from_any_thread_only_on_drain_and_in_order():
    inbox = Inbox()
    seen = []
    worker = threading.Thread(target=lambda: [inbox.post(lambda i=i: seen.append(i)) for i in range(3)])
    worker.start()
    worker.join()
    assert seen == []  # nothing runs on the posting thread
    inbox.drain()
    assert seen == [0, 1, 2]


def test_inbox_raising_callback_leaves_the_rest_queued():
    inbox = Inbox()
    seen = []

    def boom():
        raise RuntimeError('bug in callback')

    for callback in (lambda: seen.append('a'), boom, lambda: seen.append('b')):
        inbox.post(callback)
    with pytest.raises(RuntimeError):
        inbox.drain()
    assert seen == ['a']
    inbox.drain()
    assert seen == ['a', 'b']


@pytest.mark.parametrize('selection,devices,auto_select,expected', [
    (('h',), [ANDROID, HARMONY], True, HARMONY),
    ((), [ANDROID], True, ANDROID),
    ((), [ANDROID], False, None),  # after a failed probe the only device may not be the only one
    ((), [ANDROID, HARMONY], True, None),
    (('a', 'h'), [ANDROID, HARMONY], True, None),
    (('gone',), [ANDROID], True, None),
])
def test_resolve_target(selection, devices, auto_select, expected):
    assert resolve_target(selection, devices, auto_select) == expected


def test_install_plan_is_frozen_and_order_follows_selection():
    devices = [ANDROID, HARMONY]
    packages = {'APK': Path('a.apk'), 'HAP': None}
    plan = build_install_plan(['h', 'a'], devices, packages, {'a': 'Pixel'}.get)
    devices.clear()
    packages['APK'] = Path('other.apk')
    assert [(t.device_id, t.label, t.driver.key, t.package) for t in plan] == [
        ('h', None, 'harmony', None), ('a', 'Pixel', 'android', Path('a.apk'))]


@pytest.mark.parametrize('outcome,status', [
    (InstallOutcome(), '安装完成'), (InstallOutcome(skipped=1), '安装未完成'),
    (InstallOutcome(failed=1, skipped=1), '安装失败'), (InstallOutcome(cancelled=True, failed=1), '已中止'),
])
def test_install_status(outcome, status):
    assert outcome.status == status


def test_cancel_between_devices_stops_the_plan(monkeypatch):
    cancel = threading.Event()
    installed = []

    def install(command, stop_event):
        installed.append(command[2])
        cancel.set()  # user presses stop while the first device installs
        return InstallResult(command, subprocess.CompletedProcess(command, 0, '', ''), 0.1)

    monkeypatch.setattr(main.DRIVERS['android'], 'install', install)
    monkeypatch.setattr(main.DRIVERS['android'], 'install_command', lambda device_id, package, **kw: ['adb', '-s', device_id])
    plan = build_install_plan(['a', 'b'], [ANDROID, DeviceInfo('b', 'android', 'device')],
                              {'APK': Path('a.apk'), 'HAP': None}, str)
    messages = []
    assert run_install_plan(plan, True, cancel, messages.append).status == '已中止'
    assert installed == ['a']


# --- the App uses the runner for every device task ---------------------------------

def test_refresh_during_install_cannot_change_the_frozen_targets(app, monkeypatch, preflight, deferred_tasks):
    devices = [ANDROID, HARMONY]
    app._apply_device_refresh(devices)
    app.device_tree.selection_set('a', 'h')
    app.packages['APK'].replace([Path('a.apk')])
    app.packages['HAP'].replace([Path('h.hap')])
    preflight(devices)
    installed = []
    for key in ('android', 'harmony'):
        monkeypatch.setattr(main.DRIVERS[key], 'install', lambda command, stop_event: installed.append(command[-1])
                            or InstallResult(command, subprocess.CompletedProcess(command, 0, '', ''), 0.0))
    app.install_to_selected()
    deferred_tasks.pop(0)()  # preflight finishes; the install step is queued
    app._apply_device_refresh([])  # both devices vanish before the worker runs
    deferred_tasks.run_all()
    assert installed == ['a.apk', 'h.hap']
    assert app.install_status_var.get() == '安装完成'


def test_only_device_is_the_target_unless_the_probe_failed(app, monkeypatch, deferred_tasks):
    app._apply_device_refresh([ANDROID])
    app.device_tree.selection_remove(*app.device_tree.selection())
    app.update()
    assert app.crash_log_button.instate(['!disabled'])
    monkeypatch.setattr(main.DRIVERS['android'], 'collect_crash_log', lambda device_id, output_dir, cancel=None: (
        CollectResult(['adb', device_id], subprocess.CompletedProcess([], -1, '', '命令已中止'))))
    app.fetch_crash_log()
    assert app.tasks.current.action == 'crash_log'
    app.cancel_current_task()
    deferred_tasks.run_all()
    assert '获取崩溃日志已中止：设备 a' in app.log_text.get('1.0', 'end')
    warnings = []
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: warnings.append(args))
    app._apply_device_refresh([ANDROID], harmony_error='HDC unavailable')
    assert app.device_tree.selection() == ()
    assert app.crash_log_button.instate(['disabled'])
    app.fetch_crash_log()
    assert not app.tasks.busy and warnings[-1][1] == '请选择一个设备'


def test_udid_probe_can_be_cancelled_without_an_error_dialog(app, monkeypatch, deferred_tasks, fake_process):
    app._apply_device_refresh([HARMONY])
    warnings = []
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: warnings.append(args))
    fake_process.handler = lambda command, **kwargs: (-1, '', '', {'cancelled': kwargs['cancel'].is_set()})
    app.fetch_hdc_udid()
    assert app.install_button.cget('text') == '中止获取UDID'
    app.install_to_selected()
    deferred_tasks.run_all()
    assert fake_process.calls[0][1]['cancel'].is_set()
    assert not warnings and not app.tasks.busy
    assert app.install_status_var.get() == '已中止'
    assert '获取 UDID 已中止' in app.log_text.get('1.0', 'end')


def test_stop_during_preflight_reaches_the_device_probes(app, monkeypatch, fake_process, deferred_tasks):
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: None)  # fail, never block
    app._apply_device_refresh([ANDROID])
    app.packages['APK'].replace([Path('a.apk')])
    fake_process.handler = lambda command, **kwargs: (-1, '', '', {'cancelled': kwargs['cancel'].is_set()})
    app.install_to_selected()
    app.install_to_selected()  # stop while the probes would still be running
    deferred_tasks.run_all()
    assert len(fake_process.calls) == 2  # adb and hdc probes
    assert all(kwargs['cancel'].is_set() for _command, kwargs in fake_process.calls)
    assert app.install_status_var.get() == '已中止' and not app.tasks.busy


@pytest.fixture
def late_stop(app):
    """Stop lands after the worker finished but before its result is applied."""
    def post(callback):
        app.tasks.cancel()
        callback()
    app.tasks.post = post


def test_late_stop_does_not_relabel_a_successful_udid(app, monkeypatch, late_stop):
    app._apply_device_refresh([HARMONY])
    monkeypatch.setattr(main.messagebox, 'showinfo', lambda *args: None)
    monkeypatch.setattr(main.DRIVERS['harmony'], 'udid', lambda device_id, cancel=None: 'UDID-123')
    app.fetch_hdc_udid()
    assert app.install_status_var.get() == '获取UDID完成'
    assert app.clipboard_get() == 'UDID-123'


def test_refresh_exception_blocks_auto_target_from_the_stale_list(app, monkeypatch):
    app._apply_device_refresh([ANDROID])
    app.device_tree.selection_remove(*app.device_tree.selection())
    app.update()
    assert app.crash_log_button.instate(['!disabled'])

    def broken(cancel=None):
        raise RuntimeError('probe crashed')
    monkeypatch.setattr(main, 'detect_devices', broken)
    REAL_REFRESH_DEVICES(app)
    assert '刷新设备列表失败：probe crashed' in app.log_text.get('1.0', 'end')
    assert app.crash_log_button.instate(['disabled'])


def test_cancelled_udid_probe_is_reported_as_an_hdc_error(fake_process, hdc_executable):
    cancel = threading.Event()
    cancel.set()
    fake_process.handler = lambda command, **kwargs: (-1, '', '', {'cancelled': True})
    with pytest.raises(HdcError, match='中止'):
        main.DRIVERS['harmony'].udid('h', cancel=cancel)


def test_results_reach_the_ui_before_the_event_loop_runs(monkeypatch, tmp_path):
    """#88: with the real runner, the startup refresh is delivered while the UI
    thread is not yet in mainloop (it only pumps here, as during a slow startup
    scan). A Tk call from the worker would raise "main thread is not in main loop"."""
    monkeypatch.setattr(main.App, '_get_config_path', lambda self: tmp_path / 'config.json')
    monkeypatch.setattr(main, 'detect_devices', lambda cancel=None: DeviceDetectionResult([ANDROID]))
    window = main.App()  # real TaskRunner: refresh_devices runs on a worker thread
    errors = []
    window.report_callback_exception = lambda *error: errors.append(error)
    try:
        window.withdraw()

        def boom():
            raise RuntimeError('bug in a callback')

        worker = threading.Thread(target=lambda: window._log_threadsafe('from a worker thread'))
        worker.start()
        worker.join()
        window.inbox.post(boom)
        window.inbox.post(lambda: window.log('after the failing callback'))
        deadline = time.monotonic() + 5
        while 'after the failing callback' not in window.log_text.get('1.0', 'end') or window.refreshing:
            assert time.monotonic() < deadline, 'background results were never delivered'
            window.update()
            time.sleep(0.01)
        assert window.device_tree.get_children() == ('a',)
        assert window.refresh_button.cget('text') == '刷新设备'
        assert 'from a worker thread' in window.log_text.get('1.0', 'end')
        # A failing callback is reported and does not stop later deliveries.
        assert len(errors) == 1
    finally:
        window.destroy()
