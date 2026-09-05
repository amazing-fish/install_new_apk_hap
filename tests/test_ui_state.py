"""Real Tk widgets/events, with device commands and user config isolated."""

import os
import sys
from pathlib import Path
from tkinter import font as tkfont

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main
from services.device_detector import DeviceInfo


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(main.App, "_get_config_path", lambda self: tmp_path / "config.json")
    monkeypatch.setattr(main.App, "refresh_devices", lambda self: None)
    monkeypatch.setattr(main.App, "load_last_scan_dir", lambda self: None)
    window = main.App()
    window.withdraw()
    try:
        yield window
    finally:
        window.update_idletasks()
        window.destroy()


def assert_selection_labels(app, expected):
    assert app.selected_device_summary_var.get() == expected
    for label in (app.execution_selection_label, app.status_selection_label):
        assert app.getvar(str(label.cget("textvariable"))) == expected


def test_device_refresh_selection_rename_and_disconnect_stay_in_sync(app):
    app.config_manager.set_device_name("h", "Mate")
    devices = [DeviceInfo("a", "android", "unauthorized"), DeviceInfo("h", "harmony", "device")]
    app._apply_device_refresh(devices)
    app.update()
    assert tuple(app.device_tree.cget("displaycolumns")) == ("name", "platform", "status", "device_id")
    assert app.device_tree.set("a", "status") == "unauthorized"
    assert app.device_tree.set("a", "platform") == "Android"
    assert app.device_summary_var.get() == "总计 2 台 · Android 1 台 · Harmony 1 台"
    assert_selection_labels(app, "未选择设备")

    app.device_tree.selection_set("a", "h")
    app.update()
    assert_selection_labels(app, "已选 2 台：a，Mate")
    assert app.name_var.get() == ""

    app._apply_device_refresh(devices)
    assert_selection_labels(app, "已选 2 台：a，Mate")
    app.device_tree.selection_set("h")
    app.update()
    assert app.name_var.get() == "Mate"
    app.name_var.set("  Mate 70  ")
    app.save_device_name()
    assert app.device_tree.set("h", "name") == "Mate 70"
    assert_selection_labels(app, "已选 1 台：Mate 70")

    app.name_var.set("")
    app.save_device_name()
    app.on_device_select(None)
    assert app.name_var.get() == ""
    assert app.device_tree.set("h", "name") == ""
    assert_selection_labels(app, "已选 1 台：h")

    app.device_tree.selection_remove("h")
    app.update()
    assert_selection_labels(app, "未选择设备")
    app._apply_device_refresh([devices[1]])
    assert_selection_labels(app, "已选 1 台：h")
    app._apply_device_refresh([])
    assert app.device_summary_var.get() == "未检测到设备"
    assert app.name_var.get() == ""
    assert_selection_labels(app, "未选择设备")


def test_stale_refresh_cannot_overwrite_summaries_or_selected_names(app):
    app._latest_refresh_request_id = 2
    app._apply_device_refresh_result(2, [DeviceInfo("new", "harmony", "device")])
    app._apply_device_refresh_result(1, [DeviceInfo("stale", "android", "device")])
    app._apply_device_refresh_error(1, RuntimeError("stale error"))
    assert app.device_tree.get_children() == ("new",)
    assert app.device_summary_var.get() == "总计 1 台 · Android 0 台 · Harmony 1 台"
    assert_selection_labels(app, "已选 1 台：new")


def test_scan_dropdown_changes_empty_directory_and_test_flag(app, tmp_path):
    packages = tmp_path / "packages"
    packages.mkdir()
    for index, name in enumerate(["old.apk", "new.apk", "old.hap", "new.hap"]):
        path = packages / name
        path.touch()
        os.utime(path, (100 + index, 100 + index))
    app.config_manager.set_apk_need_t("old.apk", True)
    app.folder_var.set(str(packages))
    app.scan_latest_packages()
    assert app.package_summary_var.get() == "APK new.apk · HAP new.hap"
    assert app.apk_test_var.get() is False

    app.apk_combo.current(1)
    app.apk_combo.event_generate("<<ComboboxSelected>>")
    app.hap_combo.current(1)
    app.hap_combo.event_generate("<<ComboboxSelected>>")
    app.update()
    assert app.latest_apk == packages / "old.apk"
    assert app.latest_hap == packages / "old.hap"
    assert app.apk_test_var.get() is True
    assert app.package_summary_var.get() == "APK old.apk · HAP old.hap"

    empty = tmp_path / "empty"
    empty.mkdir()
    app.folder_var.set(str(empty))
    app.scan_latest_packages()
    assert app.latest_apk is None and app.latest_hap is None
    assert app.package_summary_var.get() == "未找到可安装包"
    assert str(app.apk_combo.cget("state")) == "disabled"
    assert str(app.hap_combo.cget("state")) == "disabled"
    assert app.apk_test_var.get() is False


def test_package_display_changes_do_not_mutate_install_click_snapshot(app, monkeypatch):
    devices = [DeviceInfo("a", "android", "device"), DeviceInfo("h", "harmony", "device")]
    app._apply_device_refresh(devices)
    app.device_tree.selection_set("a", "h")
    app.latest_apk, app.latest_hap = Path("original.apk"), Path("original.hap")
    app.apk_test_var.set(True)
    scheduled = []

    class DeferredThread:
        def __init__(self, *, target, args, daemon):
            self.target, self.args = target, args

        def start(self):
            scheduled.append(self)

    monkeypatch.setattr(main.threading, "Thread", DeferredThread)
    app.install_to_selected()
    snapshot = scheduled[0].args
    app.apk_name_map = {"next.apk": Path("next.apk")}
    app.apk_var.set("next.apk")
    app.on_apk_selected(None)
    app.hap_name_map = {"next.hap": Path("next.hap")}
    app.hap_var.set("next.hap")
    app.on_hap_selected(None)
    app.device_tree.selection_remove("a", "h")
    app.update()
    assert app.package_summary_var.get() == "APK next.apk · HAP next.hap"
    assert app.apk_test_var.get() is False

    app._finalize_install(devices, *snapshot)
    assert scheduled[1].args == (["a", "h"], Path("original.apk"), Path("original.hap"), True)
    assert_selection_labels(app, "已选 2 台：a，h")
    assert app.package_summary_var.get() == "APK next.apk · HAP next.hap"


def test_default_and_desktop_layout_keep_install_and_log_visible(app):
    app.attributes("-alpha", 0)
    app.deiconify()
    app._apply_device_refresh([
        DeviceInfo("a", "android", "device"), DeviceInfo("h", "harmony", "device")
    ])
    app.device_tree.selection_set("a", "h")
    app.latest_apk, app.latest_hap = Path("demo.apk"), Path("demo.hap")
    app._update_package_summary()
    for geometry in ("500x600", "800x700"):
        app.geometry(geometry)
        app.update()
        log_font = tkfont.Font(root=app, font=app.log_text.cget("font"))
        log_min_height = log_font.metrics("linespace") + 2 * (
            int(app.log_text.cget("pady")) + int(app.log_text.cget("borderwidth"))
            + int(app.log_text.cget("highlightthickness"))
        )
        for widget in (app.install_button, app.log_text, app.status_selection_label):
            assert widget.winfo_ismapped()
            required_height = log_min_height if widget is app.log_text else widget.winfo_reqheight()
            assert widget.winfo_height() >= required_height
            y = widget.winfo_rooty() - app.winfo_rooty()
            assert 0 <= y < y + widget.winfo_height() <= app.winfo_height()
