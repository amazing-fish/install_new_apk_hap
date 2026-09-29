import subprocess
from pathlib import Path
from tkinter import ttk

import pytest

import main
from ui_styles import DEFAULT_GEOMETRY
from platforms import DeviceInfo
from platforms.base import CollectResult, InstallResult


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
@pytest.mark.parametrize('geometry', ['480x560', DEFAULT_GEOMETRY, '1024x800'])
def test_long_content_controls_reflow_and_keyboard_reveals_log(app, geometry):
    show(app, geometry)
    devices = [DeviceInfo(f'device-{i:02d}-'+ 'x'*80, 'harmony', 'device') for i in range(20)]
    app.config_manager.data['device_names'] = {d.device_id: '长名称'*20 for d in devices}
    app._apply_device_refresh(devices)
    app.device_tree.selection_set(*[d.device_id for d in devices])
    app.packages['APK'].replace([Path('long-'*30+'.apk')])
    app.packages['HAP'].replace([Path('long-'*30+'.hap')])
    app._render_packages()
    app.update()
    assert_visible(app, app.install_button)
    assert_visible(app, app.status_selection_label)
    canvas = app.scroll_area.canvas
    page_needs_scroll = app.scroll_area.content.winfo_height() > canvas.winfo_height()
    if page_needs_scroll:
        assert canvas.yview()[1] < 1
    else:
        assert canvas.yview() == (0, 1)
    assert bool(app.scroll_area.scrollbar.winfo_ismapped()) is page_needs_scroll
    assert app.device_v_scrollbar.winfo_ismapped()
    assert app.device_h_scrollbar.winfo_ismapped()
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


@pytest.mark.parametrize('app', [1.0, 1.5, 1.67], indirect=True)
def test_default_window_shows_device_packages_and_log_without_page_scroll(app):
    # The startup size scales with the display, so use what the app opened with.
    show(app, app.geometry().split('+')[0])
    app._apply_device_refresh([DeviceInfo('android-a', 'android', 'device'),
                              DeviceInfo('harmony-b', 'harmony', 'device')])
    app.device_tree.selection_set('android-a')
    app.packages['APK'].replace([Path('demo.apk')])
    app._render_packages()
    app.update()
    for control in (app.device_tree, app.name_entry, app.scan_button, app.apk_combo,
                    app.hap_combo, app.log_text, app.install_button):
        assert_visible(app, control)
    assert app.scroll_area.canvas.yview() == (0, 1)
    assert not app.scroll_area.scrollbar.winfo_ismapped()
    assert not app.device_v_scrollbar.winfo_ismapped()
    assert not app.device_h_scrollbar.winfo_ismapped()
    app.clear_log()
    app.update()
    assert not app.log_v_scrollbar.winfo_ismapped()
    assert not app.log_h_scrollbar.winfo_ismapped()
    # Name/folder actions stay alongside their field in the ordinary window.
    assert app.name_entry.actions.buttons[0].winfo_rooty() == app.name_entry.actions.buttons[1].winfo_rooty()


def test_package_display_has_no_redundant_summary_row(app):
    def label_texts():
        return [app.getvar(str(widget.cget('textvariable'))) if str(widget.cget('textvariable'))
                else str(widget.cget('text'))
                for widget in descendants(app.scroll_area.content) if isinstance(widget, ttk.Label)]

    def use_apk(name):
        app.packages['APK'].replace([Path(name)])
        app._render_packages()
        app.update()

    show(app, DEFAULT_GEOMETRY)
    app._apply_device_refresh([DeviceInfo('a', 'android', 'device')])
    use_apk('short.apk')
    # The dropdown is the only place the package appears.
    assert not any('short.apk' in text for text in label_texts())
    assert not app.execution_selection_label.winfo_ismapped()
    app.config_manager.data['device_names'] = {'a': '长设备名称' * 30}
    app._update_selected_device_summary()
    use_apk('long-name-' * 30 + '.apk')
    assert app.execution_selection_label.winfo_ismapped()
    assert not any('long-name-' in text for text in label_texts())
    app.config_manager.data['device_names'] = {'a': 'A'}
    app._update_selected_device_summary()
    use_apk('short.apk')
    assert not app.execution_selection_label.winfo_ismapped()


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
    assert app.log_v_scrollbar.winfo_ismapped()
    assert app.log_h_scrollbar.winfo_ismapped()
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
    # Background wheel belongs to the outer page when an outer page exists.
    app.scroll_area.canvas.yview_moveto(0)
    page_needs_scroll = app.scroll_area.content.winfo_height() > app.scroll_area.canvas.winfo_height()
    app.scroll_area.content.event_generate('<MouseWheel>', delta=-120)
    app.update()
    if page_needs_scroll:
        assert app.scroll_area.canvas.yview()[0] > 0
    else:
        assert app.scroll_area.canvas.yview() == (0, 1)


def test_platform_actions_follow_selection_and_busy_completion(app, monkeypatch, deferred_tasks):
    devices = [DeviceInfo('a','android','device'), DeviceInfo('h','harmony','device')]
    app._apply_device_refresh(devices)
    assert app.udid_button.instate(['disabled'])
    app.device_tree.selection_set('a')
    app.update()
    assert app.crash_log_button.instate(['!disabled'])
    assert app.udid_button.instate(['disabled']) and app.app_log_button.instate(['disabled'])
    app.device_tree.selection_set('h')
    app.update()
    assert app.udid_button.instate(['!disabled'])
    assert app.app_log_button.instate(['!disabled'])
    monkeypatch.setattr(main.messagebox, 'showinfo', lambda *args: None)
    monkeypatch.setattr(main.DRIVERS['harmony'], 'collect_app_log', lambda *args, **kwargs: CollectResult(
        ['hdc'], subprocess.CompletedProcess(['hdc'], 0, '', ''), zip_path=Path('D:/qk.zip'), file_count=1))
    app.fetch_qiankun_log()
    assert all(button.instate(['disabled']) for button in (app.udid_button, app.crash_log_button, app.app_log_button))
    assert app.app_log_button.cget('text') == '获取乾崑日志中…'
    app.device_tree.selection_set('a')
    app.update()
    deferred_tasks.run_all()
    assert app.app_log_button.cget('text') == '获取APP日志'
    assert app.install_status_var.get() == '获取乾崑日志完成'
    assert app.udid_button.instate(['disabled'])
    assert app.crash_log_button.instate(['!disabled'])
    app._set_refresh_state(True)
    assert app.crash_log_button.instate(['disabled'])
    assert app.refresh_button.cget('text') == app.scan_button.cget('text') == '刷新中…'
    app._set_refresh_state(False)
    assert app.crash_log_button.instate(['!disabled'])
    app.packages['HAP'].replace([Path('demo.hap')])
    app.install_to_selected()
    assert app.install_button.cget('text') == '中止安装'
    assert app.crash_log_button.instate(['disabled'])
    app.install_to_selected()  # the same button stops the task
    assert app.install_button.instate(['disabled'])
    assert app.install_status_var.get() == '正在中止'
    deferred_tasks.run_all()
    assert app.install_status_var.get() == '已中止'
    assert app.install_button.cget('text') == '安装到所选设备'
    assert app.install_button.instate(['!disabled'])


@pytest.mark.parametrize('outcome,status', [(0,'安装完成'), (1,'安装失败'), ('raise','安装异常'), ('stop','已中止'), ('skip','安装未完成')])
def test_install_status_distinguishes_failure_cancel_and_skips(app, monkeypatch, preflight, outcome, status):
    devices = [DeviceInfo('h','harmony','device')]
    app._apply_device_refresh(devices)
    preflight(devices)
    if outcome == 'skip':
        app.packages['APK'].replace([Path('demo.apk')])  # nothing a Harmony device can install
    else:
        app.packages['HAP'].replace([Path('demo.hap')])
    def install(command, stop_event):
        assert command[0] and stop_event is app.tasks.current.cancel
        if outcome == 'raise':
            raise RuntimeError('failed command')
        if outcome == 'stop':
            stop_event.set()
        code = 1 if outcome in (1, 'stop') else 0
        return InstallResult(command=['hdc'], process=subprocess.CompletedProcess([],code,'',''), duration_seconds=0)
    monkeypatch.setattr(main.DRIVERS['harmony'], 'install', install)
    app.install_to_selected()
    app.update()
    assert app.install_status_var.get() == status
    assert not app.tasks.busy
    assert app.install_button.instate(['!disabled'])
    assert status in app.log_text.get('1.0','end')


def test_preflight_and_udid_exceptions_restore_controls(app, monkeypatch):
    app._apply_device_refresh([DeviceInfo('h','harmony','device')])
    warnings = []
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: warnings.append(args))
    def broken(*args, **kwargs):
        raise RuntimeError('probe failed')
    monkeypatch.setattr(main, 'detect_devices', broken)
    app.packages['HAP'].replace([Path('demo.hap')])
    app.install_to_selected()
    app.update()
    assert not app.tasks.busy and app.install_status_var.get() == '安装异常'
    monkeypatch.setattr(main.DRIVERS['harmony'], 'udid', broken)
    app.fetch_hdc_udid()
    app.update()
    assert not app.tasks.busy and app.udid_button.instate(['!disabled'])
    assert app.install_status_var.get() == '获取UDID失败'
    assert len(warnings) == 2
