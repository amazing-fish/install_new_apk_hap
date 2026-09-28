"""The folder field is editable: Enter scans the typed directory (#85)."""
import main


def press_enter(app, key='Return'):
    if not app.winfo_viewable():  # key events need a mapped, focused window
        app.attributes('-alpha', 0)
        app.deiconify()
    app.folder_entry.focus_force()
    app.update()
    app.folder_entry.event_generate(f'<{key}>')
    app.update()


def test_enter_scans_typed_directory_and_remembers_it(app, tmp_path):
    (tmp_path / 'demo.apk').touch()
    app.folder_var.set(f'  {tmp_path}  ')
    press_enter(app)
    assert app.packages['APK'].selected == tmp_path / 'demo.apk'
    assert app.config_manager.data['last_scan_dir'] == str(tmp_path)
    log = app.log_text.get('1.0', 'end')
    assert f'已选择安装包目录: {tmp_path}' in log
    assert '安装包扫描完成' in log


def test_keypad_enter_is_bound_too(app):
    # Windows reports keypad Enter as <Return>; X11 sends a distinct KP_Enter.
    assert 'submit_folder' in app.folder_entry.bind('<KP_Enter>')
    assert 'submit_folder' in app.folder_entry.bind('<Return>')


def test_enter_on_invalid_directory_warns_and_keeps_last_dir(app, tmp_path, monkeypatch):
    app.config_manager.set_last_scan_dir(str(tmp_path))
    warnings = []
    monkeypatch.setattr(main.messagebox, 'showwarning', lambda *args: warnings.append(args))
    app.folder_var.set(str(tmp_path / 'missing'))
    press_enter(app)
    assert warnings[-1][1] == '目录不存在或不是目录'
    assert app.config_manager.data['last_scan_dir'] == str(tmp_path)


def test_enter_on_the_current_directory_rescans_without_duplicate_log(app, tmp_path):
    (tmp_path / 'demo.apk').touch()
    app.folder_var.set(str(tmp_path))
    press_enter(app)
    before = app.log_text.get('1.0', 'end')
    press_enter(app)
    # Unchanged folder and files: nothing new to report.
    assert app.log_text.get('1.0', 'end') == before
