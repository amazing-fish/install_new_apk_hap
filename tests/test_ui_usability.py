import subprocess
from pathlib import Path
from tkinter import ttk

import pytest

import main
from services.device_detector import DeviceInfo
from services.installer import InstallResult


def show(app, geometry='480x560'):
    app.attributes('-alpha', 0)
    app.geometry(geometry)
    app.deiconify()
    app.update()


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def assert_visible(app, widget):
    x = widget.winfo_rootx() - app.winfo_rootx()
    y = widget.winfo_rooty() - app.winfo_rooty()
    assert widget.winfo_ismapped()
    assert 0 <= x < x + widget.winfo_width() <= app.winfo_width()
    assert 0 <= y < y + widget.winfo_height() <= app.winfo_height()


@pytest.mark.parametrize('app', [1.0, 1.5, 2.0], indirect=True)
@pytest.mark.parametrize('geometry', ['480x560', '720x780', '1024x800'])
def test_long_content_controls_reflow_and_keyboard_reveals_log(app, geometry):
    show(app, geometry)
    devices = [DeviceInfo(f'device-{i:02d}-'+ 'x'*80, 'harmony', 'device') for i in range(20)]
    app.config_manager.data['device_names'] = {d.device_id: '长名称'*20 for d in devices}
    app._apply_device_refresh(devices)
    app.device_tree.selection_set(*[d.device_id for d in devices])
    app.latest_apk, app.latest_hap = Path('long-'*30+'.apk'), Path('long-'*30+'.hap')
    app._update_package_summary()
    app.update()
    assert_visible(app, app.install_button)
    assert_visible(app, app.status_selection_label)
    assert app.scroll_area.canvas.yview()[1] < 1
    canvas = app.scroll_area.canvas
    for button in descendants(app.scroll_area.content):
        if isinstance(button, ttk.Button):
            assert button.winfo_width() >= button.winfo_reqwidth()
            assert button.winfo_rootx() + button.winfo_width() <= canvas.winfo_rootx() + canvas.winfo_width()
    app.device_tree.yview_moveto(1)
    app.device_tree.xview_moveto(1)
    assert app.device_tree.yview()[1] == 1
    assert app.device_tree.xview()[1] == 1
    total_width = sum(app.device_tree.column(c, 'width') for c in app.device_tree['columns'])
    if total_width > app.device_tree.winfo_width():
        assert app.device_tree.xview()[0] > 0
    last = devices[-1].device_id
    assert app.device_tree.bbox(last, 'device_id')
    app.log_text.focus_force()
    app.update()
    assert_visible(app, app.log_text)
    assert_visible(app, app.install_button)
    app.log_text.event_generate('<Control-Home>')
    app.update()
    assert canvas.yview()[0] == 0
    app.log_text.event_generate('<Control-End>')
    app.update()
    assert canvas.yview()[1] == 1


def test_tab_visits_actions_and_nested_wheel_does_not_move_page(app):
    show(app)
    app._apply_device_refresh([DeviceInfo('h', 'harmony', 'device')])
    app.apk_combo.configure(values=[f'package-{i}.apk' for i in range(25)], state='readonly')
    app.apk_combo.current(0)
    app.update()
    app.name_entry.focus_force()
    app.update()
    visited = set()
    for _ in range(45):
        focused = app.focus_get()
        visited.add(focused)
        assert_visible(app, focused)
        focused.event_generate('<Tab>')
        app.update()
    assert {app.install_button, app.scan_button, app.apk_combo, app.log_text} <= visited
    for index in range(60):
        app.log(f'{index}: ' + 'long-output-' * 50)
    app.log_text.focus_force()
    app.update()
    page_before = app.scroll_area.canvas.yview()
    text_before = app.log_text.yview()
    app.log_text.event_generate('<MouseWheel>', delta=120)
    app.update()
    assert app.scroll_area.canvas.yview() == page_before
    assert app.log_text.yview() != text_before
    app.log_text.xview_moveto(1)
    assert app.log_text.xview()[0] > 0
    app.apk_combo.focus_force()
    app.update()
    page_before = app.scroll_area.canvas.yview()
    app.apk_combo.event_generate('<MouseWheel>', delta=-120)
    app.update()
    assert app.scroll_area.canvas.yview() == page_before
    # Background wheel belongs to the outer page.
    app.scroll_area.canvas.yview_moveto(0)
    app.scroll_area.content.event_generate('<MouseWheel>', delta=-120)
    app.update()
    assert app.scroll_area.canvas.yview()[0] > 0


def test_platform_actions_follow_selection_and_busy_completion(app):
    devices = [DeviceInfo('a','android','device'), DeviceInfo('h','harmony','device')]
    app._apply_device_refresh(devices)
    assert app.udid_button.instate(['disabled'])
    app.device_tree.selection_set('a')
    app.update()
    assert app.crash_log_button.instate(['!disabled'])
    assert app.udid_button.instate(['disabled']) and app.nextdemo_log_button.instate(['disabled'])
    app.device_tree.selection_set('h')
    app.update()
    assert app.udid_button.instate(['!disabled'])
    app._set_crash_log_fetch_state(True, 'NEXTdemo日志')
    assert all(button.instate(['disabled']) for button in (app.udid_button, app.crash_log_button, app.nextdemo_log_button))
    assert app.nextdemo_log_button.cget('text') == '获取NEXTdemo日志中…'
    app.device_tree.selection_set('a')
    app.update()
    app._set_crash_log_fetch_state(False)
    assert app.udid_button.instate(['disabled'])
    assert app.crash_log_button.instate(['!disabled'])
    app._set_refresh_state(True)
    assert app.crash_log_button.instate(['disabled'])
    assert app.refresh_button.cget('text') == app.scan_button.cget('text') == '刷新中…'
    app._set_refresh_state(False)
    assert app.crash_log_button.instate(['!disabled'])
    app._set_install_state(True)
    assert app.install_button.cget('text') == '中止安装'
    assert app.crash_log_button.instate(['disabled'])
    app.request_stop_install()
    assert app.install_button.instate(['disabled'])
    assert app.install_status_var.get() == '正在中止'
    app._finish_install('已中止')
    assert app.install_button.cget('text') == '安装到所选设备'


@pytest.mark.parametrize('outcome,status', [(0,'安装完成'), (1,'安装失败'), ('raise','安装异常'), ('stop','已中止'), ('skip','安装未完成')])
def test_install_status_distinguishes_failure_cancel_and_skips(app, monkeypatch, outcome, status):
    app._apply_device_refresh([DeviceInfo('h','harmony','device')])
    app._set_install_state(True)
    def install(*args):
        if outcome == 'raise':
            raise RuntimeError('failed command')
        if outcome == 'stop':
            app.install_stop_event.set()
        code = 1 if outcome in (1, 'stop') else 0
        return InstallResult(command=['hdc'], process=subprocess.CompletedProcess([],code,'',''), duration_seconds=0)
    monkeypatch.setattr(main, 'install_harmony', install)
    app._install_worker(['h'], None, None if outcome == 'skip' else Path('demo.hap'), False)
    app.update()
    assert app.install_status_var.get() == status
    assert not app.installing
    assert app.install_button.instate(['!disabled'])
    assert status in app.log_text.get('1.0','end')


def test_preflight_and_udid_exceptions_restore_controls(app, monkeypatch):
    app._apply_device_refresh([DeviceInfo('h','harmony','device')])
    warnings = []
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: warnings.append(args))
    def broken(*args):
        raise RuntimeError('probe failed')
    monkeypatch.setattr(main, 'detect_devices', broken)
    app._set_install_state(True)
    app._prepare_install_worker({'h'}, None, Path('demo.hap'), False)
    app.update()
    assert not app.installing and app.install_status_var.get() == '安装异常'
    monkeypatch.setattr(main, 'get_hdc_device_udid', broken)
    app._set_udid_fetch_state(True)
    app._fetch_hdc_udid_worker('h')
    app.update()
    assert not app.udid_fetching and app.udid_button.instate(['!disabled'])
    assert len(warnings) == 2
