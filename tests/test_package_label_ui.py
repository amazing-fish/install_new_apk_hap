import os
import threading
import time

from infra.tools import MetadataTools
from metadata import PackageLabel
from metadata import loader as loader_module
from metadata.loader import file_fingerprint
from packages import apk_allow_test


def pump_until(app, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    assert predicate()


def test_background_label_update_preserves_choice_and_logs(app, tmp_path, monkeypatch):
    paths = [tmp_path/'old.apk', tmp_path/'new.apk']
    for index, path in enumerate(paths):
        path.touch(); os.utime(path, (100+index, 100+index))
    entered, release = threading.Event(), threading.Event()
    worker_threads = []
    monkeypatch.setattr(loader_module, 'resolve_metadata_tools', lambda: MetadataTools())
    def parse(path, tools):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert release.wait(3)
        return PackageLabel(
            '同名应用', 'resolved', package_name='com.example.demo',
            version_name='1.2.3', version_code=123,
        )
    monkeypatch.setattr(loader_module, 'read_package_label', parse)
    app.folder_var.set(str(tmp_path))
    try:
        app.scan_latest_packages()
        assert entered.wait(2)
        # A Tk event runs while metadata IO is blocked.
        events = []
        app.after(0, lambda: events.append('responsive'))
        app.update()
        assert events == ['responsive']
        app.apk_combo.current(1)  # newest first: index 1 is old.apk
        app.on_package_selected('APK')
        log_before = app.log_text.get('1.0', 'end')
        release.set()
        # Delivered through the inbox by the real poll, not by the test.
        pump_until(app, lambda: '同名应用' in app.apk_combo.get())
        # Both files now share a display name; the index still means old.apk.
        assert app.packages['APK'].selected == paths[0]
        assert app.apk_combo.current() == 1
        assert app.apk_combo.get() == '同名应用 · 1.2.3 (123)（old.apk）'
        assert app.log_text.get('1.0', 'end') == log_before
        assert all(t != threading.get_ident() for t in worker_threads)
    finally:
        release.set()


def test_stale_generation_and_changed_file_are_ignored(app, tmp_path):
    path = tmp_path/'one.apk'; path.touch()
    app.folder_var.set(str(tmp_path))
    app.scan_latest_packages()
    # Deliver by hand to prove attribution independently of thread timing.
    current = app._package_label_request
    app._on_package_labels(current - 1, {path: PackageLabel('Old scan', 'resolved')},
                           {path: file_fingerprint(path)})
    assert app.apk_combo.get() == path.name
    fingerprint = file_fingerprint(path)
    path.write_bytes(b'new content')
    app._on_package_labels(current, {path: PackageLabel('Old bytes', 'resolved')}, {path: fingerprint})
    assert app.apk_combo.get() == path.name
    app._on_package_labels(current, {path: PackageLabel('Current', 'resolved')}, {path: file_fingerprint(path)})
    assert app.apk_combo.get() == 'Current（one.apk）'
    empty = tmp_path/'empty'; empty.mkdir()
    app.folder_var.set(str(empty)); app.scan_latest_packages()
    assert app.packages['APK'].selected is None and app.apk_combo.get() == '未找到'


def test_metadata_apply_does_not_mutate_install_click_snapshot(app, tmp_path, deferred_tasks, preflight,
                                                              install_plans):
    from platforms import DeviceInfo
    path = tmp_path/'app.apk'; path.touch()
    devices = [DeviceInfo('a', 'android', 'device')]
    app._apply_device_refresh(devices); app.device_tree.selection_set('a')
    app.packages['APK'].replace([path])
    preflight(devices)
    # No metadata at click time => safe permissive snapshot.
    app.install_to_selected()
    # A later precise result may change future installs, not the in-flight one.
    app._apply_package_labels({path: PackageLabel('Renamed display', 'resolved', test_only=False)})
    deferred_tasks.run_all()
    assert install_plans == [([('a', path)], True)]
    assert apk_allow_test(app.packages['APK']) is False
