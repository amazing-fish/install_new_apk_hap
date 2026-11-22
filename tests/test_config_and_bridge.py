from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
import types
import zipfile

from bridge import InstallerBridge, _folder_dialog_type
from config_manager import ConfigManager
from metadata import PackageLabel
from metadata.cache import PersistentMetadataCache
from platforms import DeviceDetectionResult, DeviceInfo


def test_config_manager_atomic_save_and_corrupt_backup(tmp_path: Path):
    cfg_path = tmp_path / "app_config.json"
    cfg_path.write_text("{corrupt json!!!", encoding="utf-8")

    mgr = ConfigManager(cfg_path)
    assert (tmp_path / "app_config.json.bak").is_file()
    assert mgr.data["parallel_install"] is True
    assert mgr.data["theme"] == "system"

    mgr.set_device_name("dev-1", "主力测试机")
    mgr.set_last_scan_dir(str(tmp_path))
    mgr.update_settings({"theme": "dark", "max_concurrency": 6})

    reloaded = ConfigManager(cfg_path)
    assert reloaded.data["device_names"]["dev-1"] == "主力测试机"
    assert reloaded.data["recent_dirs"][0] == str(tmp_path)
    assert reloaded.data["theme"] == "dark"
    assert reloaded.data["max_concurrency"] == 6


def test_bridge_scan_and_drag_drop_selects_dropped_package(tmp_path: Path):
    older = tmp_path / "older.hap"
    newer = tmp_path / "newer.hap"
    for target, label in ((older, "旧应用"), (newer, "新应用")):
        with zipfile.ZipFile(target, "w") as zf:
            zf.writestr(
                "module.json",
                json.dumps({"app": {"bundleName": "com.test.demo", "versionName": "1.0", "versionCode": 1, "label": label}}),
            )
    # Force newer to have a higher mtime than older.
    import os

    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_700_001_000, 1_700_001_000))

    events: list[tuple[str, dict]] = []
    bridge = InstallerBridge(
        config_path=tmp_path / "cfg.json",
        emit=lambda kind, payload: events.append((kind, payload)),
        auto_start=False,
    )
    try:
        # Drag-and-drop specifically the OLDER hap file -> should switch to its folder AND select older.hap!
        res = bridge.handle_dropped_paths([str(older)])
        assert res["ok"] is True

        # Wait briefly for background scan & metadata parse
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            state = bridge.get_initial_state()
            hap_slot = state["packages"]["HAP"]
            if (
                not state["scanning"]
                and hap_slot["candidates"]
                and hap_slot["selectedIndex"] >= 0
                and hap_slot["candidates"][hap_slot["selectedIndex"]]["labelLoaded"]
            ):
                break
            time.sleep(0.05)

        state = bridge.get_initial_state()
        hap_slot = state["packages"]["HAP"]
        assert len(hap_slot["candidates"]) == 2
        assert hap_slot["selectedIndex"] >= 0
        selected = hap_slot["candidates"][hap_slot["selectedIndex"]]
        assert selected["filename"] == "older.hap"
        assert selected["appName"] == "旧应用"
        assert selected["packageName"] == "com.test.demo"
    finally:
        bridge.close()


def test_folder_dialog_type_supports_pywebview_5_and_6():
    v6 = types.SimpleNamespace(FileDialog=types.SimpleNamespace(FOLDER="fd-v6"))
    v5 = types.SimpleNamespace(FOLDER_DIALOG="fd-v5")
    assert _folder_dialog_type(v6) == "fd-v6"
    assert _folder_dialog_type(v5) == "fd-v5"


def test_bridge_close_cancels_active_task_and_waits(tmp_path: Path):
    bridge = InstallerBridge(config_path=tmp_path / "cfg.json", emit=lambda *_: None, auto_start=False)
    task = bridge.tasks.start("install", "安装", verb="")
    assert task is not None
    finished = threading.Event()

    def long_work():
        task.cancel.wait(timeout=5.0)
        finished.set()
        return "done"

    bridge.tasks.run(task, long_work, lambda _r: None, lambda _e: None)
    bridge.close(timeout=3.0)
    assert task.cancelled is True
    assert finished.is_set()
    assert not bridge.tasks.busy


def test_bridge_stale_device_refresh_ignored_and_failed_scan_preserves_folder(tmp_path: Path):
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "app_a.apk").write_bytes(b"apk-a")

    bridge = InstallerBridge(config_path=tmp_path / "cfg.json", emit=lambda *_: None, auto_start=False)
    try:
        # Stale refresh_request_id cannot overwrite newer device list
        bridge._latest_refresh_request_id = 2
        bridge._apply_device_refresh_result(
            1, DeviceDetectionResult(devices=[DeviceInfo("old-dev", "android", "device")])
        )
        assert bridge.devices == []

        # Scan dir_a synchronously via inline spawn
        bridge.tasks.spawn = lambda fn: fn()
        assert bridge.scan_folder(str(dir_a))["ok"] is True
        assert bridge.folder == str(dir_a)
        assert bridge.packages["APK"].selected.name == "app_a.apk"

        # Failed scan of missing dir_b must keep folder=dir_a and its APK slot
        res_bad = bridge.scan_folder(str(tmp_path / "does_not_exist"))
        assert res_bad["ok"] is False
        assert bridge.folder == str(dir_a)
        assert bridge.packages["APK"].selected.name == "app_a.apk"

        # start_install is blocked while scanning is True
        bridge.scanning = True
        assert bridge.start_install([])["ok"] is False
        bridge.scanning = False
    finally:
        bridge.close()


def test_bridge_config_permission_error_does_not_block_scan(tmp_path: Path, monkeypatch):
    pkg_dir = tmp_path / "pkgs"
    pkg_dir.mkdir()
    (pkg_dir / "demo.apk").write_bytes(b"apk")

    bridge = InstallerBridge(config_path=tmp_path / "cfg.json", emit=lambda *_: None, auto_start=False)
    try:
        bridge.tasks.spawn = lambda fn: fn()
        monkeypatch.setattr(
            bridge.config_manager,
            "set_last_scan_dir",
            lambda _p: (_ for _ in ()).throw(PermissionError("read-only config")),
        )
        res = bridge.scan_folder(str(pkg_dir), remember=True)
        assert res["ok"] is True
        assert bridge.scanning is False
        assert bridge.folder == str(pkg_dir)
        assert bridge.packages["APK"].selected.name == "demo.apk"
    finally:
        bridge.close()


def test_bridge_select_package_rejects_stale_revision(tmp_path: Path):
    (tmp_path / "a.apk").write_bytes(b"a")
    (tmp_path / "b.apk").write_bytes(b"b")
    bridge = InstallerBridge(config_path=tmp_path / "cfg.json", emit=lambda *_: None, auto_start=False)
    try:
        bridge.tasks.spawn = lambda fn: fn()
        bridge.scan_folder(str(tmp_path))
        rev1 = bridge.packages["APK"].revision
        bridge.scan_folder(str(tmp_path))
        rev2 = bridge.packages["APK"].revision
        assert rev2 > rev1
        stale = bridge.select_package("APK", 1, revision=rev1)
        assert stale["ok"] is False and stale.get("stale") is True
        fresh = bridge.select_package("APK", 1, revision=rev2)
        assert fresh["ok"] is True
    finally:
        bridge.close()


def test_finalize_install_never_substitutes_disconnected_selection_and_uses_preflight_snapshot(
    tmp_path: Path, monkeypatch
):
    import bridge as bridge_mod

    (tmp_path / "app.apk").write_bytes(b"apk")
    bridge = InstallerBridge(config_path=tmp_path / "cfg.json", emit=lambda *_: None, auto_start=False)
    try:
        bridge.tasks.spawn = lambda fn: fn()
        bridge.scan_folder(str(tmp_path))
        dev_a = DeviceInfo("dev-a", "android", "device")
        dev_b = DeviceInfo("dev-b", "android", "device")
        bridge._apply_device_refresh([dev_a, dev_b])

        planned: list[list[str]] = []
        monkeypatch.setattr(
            bridge_mod,
            "run_install_plan",
            lambda plan, *_args, **_kw: planned.append([t.device_id for t in plan]) or bridge_mod.InstallOutcome(),
        )

        # User explicitly selected dev-a, but preflight sees only dev-b -> must NOT install on dev-b!
        task = bridge.tasks.start("install", "安装", verb="")
        bridge._finalize_install(
            task,
            DeviceDetectionResult(devices=[dev_b]),
            previous_selection={"dev-a"},
            packages=bridge._selected_packages(),
            allow_test=True,
            parallel=False,
            max_concurrency=1,
            validation_duration=0.01,
        )
        assert planned == []
        assert any("已选设备均已断开" in entry["message"] for entry in bridge._logs)
    finally:
        bridge.close()


def test_persistent_metadata_cache_serializes_concurrent_flushes(tmp_path: Path):
    cache_path = tmp_path / "meta.json"
    cache = PersistentMetadataCache(cache_path=cache_path)
    for i in range(20):
        cache.put(f"k{i}", PackageLabel(name=f"App{i}", status="resolved"))

    errors: list[Exception] = []

    def do_flush():
        try:
            for _ in range(5):
                cache.put(f"extra-{threading.get_ident()}", PackageLabel(name="X", status="resolved"))
                cache.flush()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=do_flush) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    reloaded = PersistentMetadataCache(cache_path=cache_path)
    assert reloaded.get("k0") is not None


def test_superseded_scan_cannot_overwrite_newer_last_scan_dir(tmp_path: Path):
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "a.apk").write_bytes(b"a")
    (dir_b / "b.apk").write_bytes(b"b")

    bridge = InstallerBridge(config_path=tmp_path / "cfg.json", emit=lambda *_: None, auto_start=False)
    try:
        from packages import find_packages

        bridge._latest_scan_request_id = 2
        # Commit newer scan B first
        found_b = find_packages(dir_b)
        bridge._apply_scan_result(2, dir_b, found_b, ("b", ()), None, remember=True)
        assert bridge.config_manager.data["last_scan_dir"] == str(dir_b)

        # Late superseded scan A must NOT overwrite last_scan_dir
        found_a = find_packages(dir_a)
        bridge._apply_scan_result(1, dir_a, found_a, ("a", ()), None, remember=True)
        assert bridge.config_manager.data["last_scan_dir"] == str(dir_b)
        assert bridge.folder == str(dir_b)
    finally:
        bridge.close()


def test_update_settings_assigns_revisions_in_commit_order(tmp_path: Path):
    emitted: list[dict] = []
    bridge = InstallerBridge(
        config_path=tmp_path / "cfg.json",
        emit=lambda kind, payload: emitted.append(payload) if kind == "settings" else None,
        auto_start=False,
    )
    try:
        def update(theme: str, conc: int):
            bridge.update_settings({"theme": theme, "maxConcurrency": conc})

        threads = [
            threading.Thread(target=update, args=("dark" if i % 2 else "light", 2 + (i % 4)))
            for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(emitted) == 8
        revs = [p["rev"] for p in emitted]
        assert len(set(revs)) == 8 and set(revs) == set(range(1, 9))
        # Last committed config must match the highest-revision payload
        latest = max(emitted, key=lambda p: p["rev"])
        saved = bridge.config_manager.data
        assert latest["theme"] == saved["theme"]
        assert latest["maxConcurrency"] == saved["max_concurrency"]
    finally:
        bridge.close()


def test_finalize_install_does_not_overwrite_newer_refresh_state(tmp_path: Path, monkeypatch):
    import bridge as bridge_mod

    (tmp_path / "app.apk").write_bytes(b"apk")
    emitted: list[tuple[str, dict]] = []
    bridge = InstallerBridge(
        config_path=tmp_path / "cfg.json",
        emit=lambda et, p: emitted.append((et, p)),
        auto_start=False,
    )
    try:
        bridge.tasks.spawn = lambda fn: fn()
        bridge.scan_folder(str(tmp_path))
        dev_old = DeviceInfo("dev-old", "android", "device")
        dev_new = DeviceInfo("dev-new", "android", "device")

        planned: list[list[str]] = []
        monkeypatch.setattr(
            bridge_mod,
            "run_install_plan",
            lambda plan, *_args, **_kw: planned.append([t.device_id for t in plan]) or bridge_mod.InstallOutcome(),
        )

        def run_finalize(task, detection, preflight_refresh_id):
            bridge.tasks.run(
                task,
                lambda: None,
                lambda _v: bridge._finalize_install(
                    task,
                    detection,
                    previous_selection=set(),
                    packages=bridge._selected_packages(),
                    allow_test=True,
                    parallel=False,
                    max_concurrency=1,
                    validation_duration=0.01,
                    preflight_refresh_id=preflight_refresh_id,
                ),
                lambda err: (_ for _ in ()).throw(err),
            )

        # Case 1: newer refresh is still in flight -> preflight must not clear refreshing or install
        task1 = bridge.tasks.start("install", "安装", verb="")
        bridge._latest_refresh_request_id = 5
        bridge.refreshing = True
        run_finalize(task1, DeviceDetectionResult(devices=[dev_old]), 4)
        assert bridge.refreshing is True
        assert bridge.devices == []
        assert planned == []

        # Case 2: newer refresh already completed -> preflight must not overwrite devices/errors/selection or install
        bridge._apply_device_refresh_result(
            5,
            DeviceDetectionResult(devices=[dev_new], harmony_error="hdc err"),
        )
        assert [d.device_id for d in bridge.devices] == ["dev-new"]
        assert bridge.device_errors == {"harmony": "hdc err"}
        assert bridge.refreshing is False

        task2 = bridge.tasks.start("install", "安装", verb="")
        emitted.clear()
        run_finalize(task2, DeviceDetectionResult(devices=[dev_old]), 4)
        assert [d.device_id for d in bridge.devices] == ["dev-new"]
        assert bridge.device_errors == {"harmony": "hdc err"}
        assert not any(et == "devices" for et, _ in emitted)
        assert planned == []

        # Case 3: earlier refresh in flight + preflight cancelled -> earlier refresh still clears refreshing
        task3 = bridge.tasks.start("install", "安装", verb="")
        bridge._latest_refresh_request_id = 6
        bridge.refreshing = True
        captured_id = bridge._latest_refresh_request_id
        task3.cancel.set()
        run_finalize(task3, DeviceDetectionResult(devices=[dev_old]), captured_id)
        assert bridge._latest_refresh_request_id == 6
        bridge._apply_device_refresh_result(6, DeviceDetectionResult(devices=[dev_old]))
        assert bridge.refreshing is False
        assert [d.device_id for d in bridge.devices] == ["dev-old"]
        assert planned == []

        # Case 4: preflight completes before older in-flight refresh -> advances id so late older refresh is ignored
        task4 = bridge.tasks.start("install", "安装", verb="")
        bridge._latest_refresh_request_id = 6
        bridge.refreshing = True
        run_finalize(task4, DeviceDetectionResult(devices=[dev_new]), 6)
        assert bridge.refreshing is False
        assert [d.device_id for d in bridge.devices] == ["dev-new"]
        assert bridge._latest_refresh_request_id == 7
        assert planned == [["dev-new"]]
        bridge._apply_device_refresh_result(6, DeviceDetectionResult(devices=[dev_old]))
        assert [d.device_id for d in bridge.devices] == ["dev-new"]
    finally:
        bridge.close()


def test_clear_logs_increments_clear_gen_and_tags_events(tmp_path: Path):
    emitted: list[tuple[str, dict]] = []
    bridge = InstallerBridge(
        config_path=tmp_path / "cfg.json",
        emit=lambda et, p: emitted.append((et, p)),
        auto_start=False,
    )
    try:
        before = bridge._append_log("before clear", "info")
        assert before["clearGen"] == 0
        assert bridge.get_initial_state()["logClearGen"] == 0

        bridge.clear_logs()
        cleared_events = [p for et, p in emitted if et == "logs_cleared"]
        assert len(cleared_events) == 1
        assert cleared_events[0]["clearGen"] == 1
        assert bridge.get_initial_state()["logClearGen"] == 1

        after = bridge._append_log("after clear", "info")
        assert after["clearGen"] == 1
        assert after["id"] > before["id"]
    finally:
        bridge.close()


def test_js_api_facade_exposes_only_explicit_rpc_methods(tmp_path: Path):
    from bridge import JsApiFacade

    bridge = InstallerBridge(config_path=tmp_path / "cfg.json", emit=lambda *_: None, auto_start=False)
    try:
        facade = JsApiFacade(bridge)
        public_attrs = sorted(name for name in dir(facade) if not name.startswith("_"))
        expected = sorted([
            "get_initial_state",
            "refresh_devices",
            "set_selected_devices",
            "save_device_name",
            "choose_folder",
            "scan_folder",
            "handle_dropped_paths",
            "select_package",
            "start_install",
            "cancel_task",
            "fetch_udid",
            "fetch_crash_log",
            "fetch_app_log",
            "open_path_in_explorer",
            "choose_log_output_dir",
            "update_settings",
            "diagnose_environment",
            "clear_logs",
            "window_start_drag",
            "window_start_resize",
            "window_minimize",
            "window_toggle_maximize",
            "window_close",
        ])
        assert public_attrs == expected
        assert len(public_attrs) == 23
    finally:
        bridge.close()


def test_window_size_persistence_and_work_area_clamping(tmp_path: Path):
    from win_window import compute_initial_window_size

    cfg_path = tmp_path / "app_config.json"
    mgr = ConfigManager(cfg_path)
    mgr.set_window_size(840, 820)
    mgr.set_window_size(100, 100)  # invalid below minimum -> ignored
    reloaded = ConfigManager(cfg_path)
    assert reloaded.data["window_width"] == 840
    assert reloaded.data["window_height"] == 820

    # Clamp 860x860 cleanly onto a 1080p 150% DPI screen (1280x680 logical work area)
    w, h, (min_w, min_h) = compute_initial_window_size(None, None, work_area=(1280, 680))
    assert w == 860
    assert h == 640
    assert min_w <= w and min_h <= h


def test_log_entry_serializes_action_path_and_label(tmp_path: Path):
    emitted: list[tuple[str, dict]] = []
    bridge = InstallerBridge(
        config_path=tmp_path / "cfg.json",
        emit=lambda et, p: emitted.append((et, p)),
        auto_start=False,
    )
    try:
        entry = bridge._append_log(
            "崩溃日志已导出",
            "success",
            action_path=str(tmp_path / "crash.zip"),
            action_label="打开位置",
        )
        assert entry["actionPath"] == str(tmp_path / "crash.zip")
        assert entry["actionLabel"] == "打开位置"
        log_events = [p for et, p in emitted if et == "log"]
        assert log_events[-1]["actionPath"] == str(tmp_path / "crash.zip")
    finally:
        bridge.close()
