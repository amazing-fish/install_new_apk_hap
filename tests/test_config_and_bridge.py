from __future__ import annotations

import json
from pathlib import Path
import time
import zipfile

from bridge import InstallerBridge
from config_manager import ConfigManager


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
        selected = hap_slot["candidates"][hap_slot["selectedIndex"]]
        assert selected["filename"] == "older.hap"
        assert selected["appName"] == "旧应用"
        assert selected["packageName"] == "com.test.demo"
    finally:
        bridge.close()
