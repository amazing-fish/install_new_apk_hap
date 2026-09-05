"""Exercise the layout interface without configuration or device services."""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ui_layout import build_ui


BUTTON_ACTIONS = [
    ("刷新设备", "refresh_devices_and_packages"),
    ("扫描最新包", "refresh_devices_and_packages"),
    ("获取UDID", "fetch_hdc_udid"),
    ("获取崩溃日志", "fetch_crash_log"),
    ("获取NEXTdemo日志", "fetch_nextdemo_log"),
    ("保存名称", "save_device_name"),
    ("复制设备码", "copy_selected_device_id"),
    ("选择目录", "choose_folder"),
    ("保存此 APK 的 -t 设置", "remember_apk_need_t"),
    ("安装到所选设备", "install_to_selected"),
    ("复制日志", "copy_log"),
    ("清空日志", "clear_log"),
]


@pytest.fixture(scope="module")
def tk_root():
    root = tk.Tk()
    root.withdraw()
    try:
        yield root
    finally:
        root.destroy()


@pytest.fixture
def layout(tk_root):
    # The same builder accepts only the Tk variables and callbacks it needs.
    # No config_manager, device services, or startup methods are provided.
    host = tk.Toplevel(tk_root)
    host.withdraw()
    host.calls = []
    values = {
        "name_var": "测试机",
        "folder_var": "packages",
        "apk_var": "preset.apk",
        "hap_var": "preset.hap",
        "install_status_var": "就绪",
        "device_summary_var": "未检测到设备",
        "selected_device_summary_var": "未选择设备",
        "package_summary_var": "APK preset.apk · HAP preset.hap",
    }
    for name, value in values.items():
        setattr(host, name, tk.StringVar(master=host, value=value))
    host.apk_test_var = tk.BooleanVar(master=host, value=True)
    callbacks = {name for _, name in BUTTON_ACTIONS} | {
        "on_device_select", "on_apk_selected", "on_hap_selected"
    }
    for name in callbacks:
        setattr(host, name, lambda *args, name=name: host.calls.append(name))
    variables = {name: getattr(host, name) for name in [*values, "apk_test_var"]}
    try:
        build_ui(host)
        host.update()
        yield host, variables
    finally:
        host.update_idletasks()
        host.destroy()


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def test_layout_preserves_supplied_variables_and_does_not_run_actions(layout):
    host, variables = layout
    assert host.calls == []
    for name, variable in variables.items():
        assert getattr(host, name) is variable
    assert host.name_entry.get() == "测试机"
    assert host.apk_combo.get() == "preset.apk"
    assert host.hap_combo.get() == "preset.hap"
    assert host.apk_test_var.get() is True
    assert str(host.log_text.cget("state")) == "disabled"


@pytest.mark.parametrize("text,action", BUTTON_ACTIONS)
def test_buttons_call_the_supplied_action_once(layout, text, action):
    host, _ = layout
    button, = [
        widget for widget in descendants(host)
        if isinstance(widget, ttk.Button) and widget.cget("text") == text
    ]
    button.invoke()
    assert host.calls == [action]


def test_selection_events_and_editing_use_supplied_variables(layout):
    host, _ = layout
    host.device_tree.insert("", tk.END, iid="device-a", values=("device-a", "", "device", "Android"))
    host.device_tree.selection_set("device-a")
    host.update()
    assert host.calls == ["on_device_select"]

    for combo, expected in ((host.apk_combo, "on_apk_selected"), (host.hap_combo, "on_hap_selected")):
        host.calls.clear()
        combo.configure(values=["chosen"], state="readonly")
        combo.current(0)
        combo.event_generate("<<ComboboxSelected>>")
        host.update()
        assert host.calls == [expected]
    assert host.apk_var.get() == host.hap_var.get() == "chosen"

    host.name_entry.delete(0, tk.END)
    host.name_entry.insert(0, "新名称")
    assert host.name_var.get() == "新名称"
    checkbutton, = [widget for widget in descendants(host) if isinstance(widget, ttk.Checkbutton)]
    checkbutton.invoke()
    assert host.apk_test_var.get() is False
