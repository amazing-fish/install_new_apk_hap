import pytest

import main
from services.device_detector import DeviceInfo

REFRESH_DEVICES = main.App.refresh_devices

def show(app, width=None):
    app.attributes('-alpha', 0)
    if width is not None:
        app.geometry(f'{width}x800')
    app.deiconify()
    app.update()


def test_device_area_keeps_six_rows_with_few_devices(app):
    show(app)
    for count in (0, 1, 2, 6):
        app._apply_device_refresh([DeviceInfo(str(i), 'android', 'device') for i in range(count)])
        app.update()
        assert int(app.device_tree.cget('height')) >= 6


def test_initial_width_fits_four_device_columns(app):
    show(app)
    app.config_manager.data['device_names'] = {'Android-07A61F9F08': 'Pixel · 集成测试'}
    app._apply_device_refresh([DeviceInfo('Android-07A61F9F08', 'android', 'device'),
                              DeviceInfo('Harmony-74BD-2026', 'harmony', 'device')])
    app.update()
    columns = sum(app.device_tree.column(c, 'width') for c in app.device_tree['columns'])
    assert abs(app.device_tree.winfo_width() - columns) <= 4


def test_device_actions_use_available_width_before_wrapping(app):
    show(app, 1000)
    actions = app.refresh_button.master
    needed = sum(button.winfo_reqwidth() for button in actions.buttons) + 6 * (len(actions.buttons) - 1)
    overhead = app.winfo_width() - actions.winfo_width()
    show(app, max(480, needed + overhead + 2))
    assert len({button.winfo_y() for button in actions.buttons}) == 1


def test_unchanged_refresh_does_not_append_logs(app, tmp_path, monkeypatch):
    apk = tmp_path / 'demo.apk'
    apk.write_bytes(b'first')
    app.folder_var.set(str(tmp_path))
    devices = [DeviceInfo('a', 'android', 'device')]
    calls = []
    class DeferredThread:
        def __init__(self, *, target, args, daemon):
            calls.append((target, args))
        def start(self):
            pass
    monkeypatch.setattr(main.threading, 'Thread', DeferredThread)
    for index in range(3):
        REFRESH_DEVICES(app)
        app.scan_latest_packages()
        app._apply_device_refresh_result(app._latest_refresh_request_id, devices)
        app.update()
        if index == 0:
            first = app.log_text.get('1.0', 'end')
        else:
            assert app.log_text.get('1.0', 'end') == first
    assert len(calls) == 3
    # Equal filenames must not conceal replacement contents.
    apk.write_bytes(b'a rebuilt package with different size')
    app.scan_latest_packages()
    assert app.log_text.get('1.0', 'end') != first


def test_device_status_changes_and_preinstall_audit_are_not_suppressed(app):
    app._apply_device_refresh([DeviceInfo('a', 'android', 'device')])
    first = app.log_text.get('1.0', 'end')
    app._apply_device_refresh([DeviceInfo('a', 'android', 'unauthorized')])
    changed = app.log_text.get('1.0', 'end')
    assert changed != first
    app._apply_device_refresh([DeviceInfo('a', 'android', 'unauthorized')],
        summary_label='安装前设备校验完成（耗时 0.01 秒）')
    assert '安装前设备校验完成' in app.log_text.get('1.0', 'end')


def test_refresh_error_recovery_and_log_clear_keep_visible_results(app, tmp_path, monkeypatch):
    app.folder_var.set(str(tmp_path))
    app.scan_latest_packages()
    app._apply_device_refresh([])
    app._apply_device_refresh_error(app._latest_refresh_request_id, RuntimeError('probe failed'))
    failed = app.log_text.get('1.0', 'end')
    app._apply_device_refresh([])
    assert app.log_text.get('1.0', 'end') != failed
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: None)
    app._set_install_state(True)
    app._apply_install_preparation_error(RuntimeError('preinstall probe failed'))
    failed = app.log_text.get('1.0', 'end')
    app._apply_device_refresh([])
    assert app.log_text.get('1.0', 'end') != failed
    app.clear_log()
    app._apply_device_refresh([])
    app.scan_latest_packages()
    assert '未检测到设备' in app.log_text.get('1.0', 'end')
    assert '未找到' in app.log_text.get('1.0', 'end')

@pytest.mark.parametrize('app', [1.0, 1.67, 2.0], indirect=True)
def test_resize_and_busy_labels_keep_actions_in_natural_flow(app):
    from tkinter import font
    from ui_widgets import ActionRow
    show(app, 680)
    app._apply_device_refresh([DeviceInfo('h', 'harmony', 'device')])
    def rows(widget):
        for child in widget.winfo_children():
            if isinstance(child, ActionRow):
                yield child
            yield from rows(child)
    for busy in (False, True, False):
        app._set_crash_log_fetch_state(busy, 'NEXTdemo日志')
        for width in (680, 610, 570, 540, 520, 500, 480, 501, 541, 611, 680):
            app.geometry(f'{width}x800')
            app.update()
            for row in rows(app.scroll_area.content):
                previous = None
                for button in row.buttons:
                    assert button.winfo_width() >= button.winfo_reqwidth()
                    assert button.winfo_x() + button.winfo_width() <= row.winfo_width()
                    if previous:
                        if button.winfo_y() == previous.winfo_y():
                            assert button.winfo_x() == previous.winfo_x() + previous.winfo_width() + 6
                        else:
                            assert button.winfo_x() == 0
                            assert previous.winfo_x() + previous.winfo_width() + 6 + button.winfo_width() > row.winfo_width()
                    previous = button
            assert app.name_entry.winfo_width() >= font.nametofont('TkDefaultFont').measure('0' * 12)


def test_refresh_does_not_resize_a_user_sized_window(app):
    show(app, 620)
    app._apply_device_refresh([DeviceInfo('very-long-id-' * 20, 'harmony', 'device')])
    app.update()
    assert app.winfo_width() == 620


def test_scan_changes_and_failures_remain_visible(app, tmp_path, monkeypatch):
    import os
    older = tmp_path / 'older.apk'
    newer = tmp_path / 'newer.apk'
    older.write_bytes(b'1')
    newer.write_bytes(b'2')
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))
    app.folder_var.set(str(tmp_path))
    app.scan_latest_packages()
    app.apk_var.set('older.apk')
    app.on_apk_selected(None)
    app.clear_log()
    app.scan_latest_packages()
    assert app.latest_apk == newer
    assert 'newer.apk' in app.log_text.get('1.0', 'end')
    baseline = app.log_text.get('1.0', 'end')
    app.scan_latest_packages()
    assert app.log_text.get('1.0', 'end') == baseline
    def denied(_directory):
        raise PermissionError('scan denied')
    with monkeypatch.context() as patch:
        patch.setattr(main, 'find_latest_packages', denied)
        patch.setattr(main.messagebox, 'showwarning', lambda *args: None)
        for _ in range(2):
            app.scan_latest_packages()
    assert app.log_text.get('1.0', 'end').count('scan denied') == 2
    app.scan_latest_packages()
    assert app.log_text.get('1.0', 'end').count('newer.apk') == 2
