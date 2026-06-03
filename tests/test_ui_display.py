import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services.device_detector import DeviceInfo
from ui_display import (
    format_device_ids_for_log,
    format_device_summary,
    format_device_tree_values,
    format_package_summary,
    format_platform_label,
    format_selected_device_summary,
    get_device_display_name,
)


def test_format_device_tree_values_orders_visible_columns() -> None:
    device = DeviceInfo(device_id="R5CN1234567", platform="android", status="device")

    values = format_device_tree_values(device, {"R5CN1234567": "Pixel 8"})

    assert values == ("Pixel 8", "Android", "device", "R5CN1234567")


def test_format_device_summary_counts_connected_platforms() -> None:
    devices = [
        DeviceInfo(device_id="android-1", platform="android", status="device"),
        DeviceInfo(device_id="android-2", platform="android", status="device"),
        DeviceInfo(device_id="harmony-1", platform="harmony", status="device"),
    ]

    assert format_device_summary(devices) == "总计 3 台 · Android 2 台 · Harmony 1 台"
    assert format_device_summary([]) == "未检测到设备"


def test_format_selected_device_summary_uses_saved_names_and_ignores_missing_devices() -> None:
    devices = [
        DeviceInfo(device_id="android-1", platform="android", status="device"),
        DeviceInfo(device_id="harmony-1", platform="harmony", status="device"),
    ]
    names = {"android-1": "Pixel 8", "harmony-1": "Mate 70"}

    assert format_selected_device_summary([], devices, names) == "未选择设备"
    assert (
        format_selected_device_summary(["android-1"], devices, names)
        == "已选 1 台：Pixel 8"
    )
    assert (
        format_selected_device_summary(["missing", "harmony-1", "android-1"], devices, names)
        == "已选 2 台：Mate 70，Pixel 8"
    )


def test_format_package_summary_reflects_current_package_selection() -> None:
    assert format_package_summary(None, None) == "未找到可安装包"
    assert (
        format_package_summary(Path("build/app-debug.apk"), Path("build/entry.hap"))
        == "APK app-debug.apk · HAP entry.hap"
    )
    assert format_package_summary(Path("build/app-debug.apk"), None) == "APK app-debug.apk"


def test_existing_device_display_helpers_move_to_ui_display() -> None:
    names = {"android-1": "Pixel 8", "blank": "  "}

    assert get_device_display_name("android-1", names) == "Pixel 8"
    assert get_device_display_name("blank", names) == "blank"
    assert format_device_ids_for_log(["android-1", "unknown"], names) == "Pixel 8，unknown"
    assert format_platform_label("android") == "Android"
    assert format_platform_label("harmony") == "Harmony"
    assert format_platform_label("other") == "other"
