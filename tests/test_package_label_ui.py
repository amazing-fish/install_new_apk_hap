import os
import threading
import time

import main
from services import package_label_loader as loader_module
from services.package_label_loader import file_fingerprint
from services.package_metadata import MetadataTools, PackageLabel


def pump_until(app, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)
    assert predicate()


def test_background_label_update_preserves_choice_test_flag_and_logs(app, tmp_path, monkeypatch):
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
        return PackageLabel('同名应用', 'resolved')
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
        app.config_manager.set_apk_need_t('old.apk', True)
        app.apk_combo.current(1)
        app.on_apk_selected(None)
        log_before = app.log_text.get('1.0', 'end')
        release.set()
        pump_until(app, lambda: '同名应用' in app.apk_var.get())
        assert app.latest_apk == paths[0] and app.apk_test_var.get()
        assert app.apk_name_map[app.apk_var.get()] == paths[0]
        assert app.package_summary_var.get() == 'APK 同名应用（old.apk）'
        assert app.log_text.get('1.0', 'end') == log_before
        assert all(t != threading.get_ident() for t in worker_threads)
        app.remember_apk_need_t()
        assert app.config_manager.data['apk_needs_t'] == ['old.apk']
    finally:
        release.set()


def test_stale_generation_empty_directory_and_changed_file_are_ignored(app, tmp_path):
    path = tmp_path/'one.apk'; path.touch()
    # Control delivery to prove attribution independently of thread timing.
    app._package_candidates = ([path], [])
    app.latest_apk = path
    app._package_label_request = 22
    app._package_label_folder = str(tmp_path)
    app.folder_var.set(str(tmp_path))
    app.apk_var.set(path.name)
    q = app._package_label_loader.results
    q.put((21, {path: PackageLabel('Old directory', 'resolved')}, {path: file_fingerprint(path)}))
    app._poll_package_labels()
    assert app.apk_var.get() == path.name
    app.after_cancel(app._package_label_poll); app._package_label_poll = None
    fingerprint = file_fingerprint(path)
    path.write_bytes(b'new content')
    q.put((22, {path: PackageLabel('Old bytes', 'resolved')}, {path: fingerprint}))
    app._poll_package_labels()
    assert app.apk_var.get() == path.name
    empty = tmp_path/'empty'; empty.mkdir()
    app.folder_var.set(str(empty)); app.scan_latest_packages()
    assert app.latest_apk is None and app.apk_var.get() == '未找到'
    assert app.package_summary_var.get() == '未找到可安装包'


def test_metadata_apply_keeps_frozen_install_parameters(app, monkeypatch, tmp_path):
    from services.device_detector import DeviceInfo
    path = tmp_path/'app.apk'; path.touch()
    devices = [DeviceInfo('a', 'android', 'device')]
    app._apply_device_refresh(devices); app.device_tree.selection_set('a')
    app.latest_apk = path; app.apk_test_var.set(True)
    app._package_candidates = ([path], [])
    tasks = []
    class DeferredThread:
        def __init__(self, *, target, args, daemon):
            self.args = args
        def start(self):
            tasks.append(self.args)
    monkeypatch.setattr(main.threading, 'Thread', DeferredThread)
    app.install_to_selected()
    app._apply_package_labels({path: PackageLabel('Renamed display', 'resolved')})
    app._finalize_install(devices, *tasks[0])
    assert tasks[1] == (['a'], path, None, True)
