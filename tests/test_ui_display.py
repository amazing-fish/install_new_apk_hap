import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services.device_detector import DeviceInfo
from ui_display import (
    format_device_summary,
    format_device_tree_values,
    format_package_summary,
    format_selected_device_summary,
)


def test_device_summary_counts_detected_devices_without_claiming_readiness():
    devices = [
        DeviceInfo("a", "android", "unauthorized"),
        DeviceInfo("b", "harmony", "offline"),
        DeviceInfo("c", "future-platform", "unknown"),
    ]
    assert format_device_summary([]) == "未检测到设备"
    assert format_device_summary(devices) == "总计 3 台 · Android 1 台 · Harmony 1 台"
    assert format_device_tree_values(devices[0], {"a": " Pixel "}) == (
        "a", "Pixel", "unauthorized", "Android"
    )
    assert format_device_tree_values(devices[2], {}) == (
        "c", "", "unknown", "future-platform"
    )


def test_selection_summary_uses_only_current_unique_ids_and_name_fallback():
    devices = [DeviceInfo("a", "android", "device"), DeviceInfo("b", "harmony", "device")]
    names = {"a": " Pixel ", "b": "  "}
    assert format_selected_device_summary(["gone"], devices, names) == "未选择设备"
    assert format_selected_device_summary([], devices, names) == "未选择设备"
    assert format_selected_device_summary(["b", "a", "gone", "a"], devices, names) == (
        "已选 2 台：b，Pixel"
    )


@pytest.mark.parametrize("apk,hap,expected", [
    (None, None, "未找到可安装包"),
    (Path("包/demo.apk"), None, "APK demo.apk"),
    (None, Path("包/测试.hap"), "HAP 测试.hap"),
    (Path("a.apk"), Path("b.hap"), "APK a.apk · HAP b.hap"),
])
def test_package_summary_uses_selected_filenames(apk, hap, expected):
    assert format_package_summary(apk, hap) == expected
