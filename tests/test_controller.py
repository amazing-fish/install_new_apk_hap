"""Tk-free task scheduling and single-device rules."""
import subprocess
import threading
from pathlib import Path

import pytest

import main
from controller import InstallOutcome, TaskRunner, build_install_plan, resolve_target, run_install_plan
from infra.tools import HdcError
from platforms import DeviceInfo
from platforms.base import CollectResult, InstallResult

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
    app.latest_apk, app.latest_hap = Path('a.apk'), Path('h.hap')
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


def test_cancelled_udid_probe_is_reported_as_an_hdc_error(fake_process, hdc_executable):
    cancel = threading.Event()
    cancel.set()
    fake_process.handler = lambda command, **kwargs: (-1, '', '', {'cancelled': True})
    with pytest.raises(HdcError, match='中止'):
        main.DRIVERS['harmony'].udid('h', cancel=cancel)
