from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple

from services.device_detector import DeviceInfo


PLATFORM_LABELS = {
    "android": "Android",
    "harmony": "Harmony",
}


def get_device_display_name(device_id: str, name_mapping: Dict[str, str]) -> str:
    name = name_mapping.get(device_id, "").strip()
    return name or device_id


def format_device_ids_for_log(device_ids: Iterable[str], name_mapping: Dict[str, str]) -> str:
    return "，".join(get_device_display_name(device_id, name_mapping) for device_id in device_ids)


def format_platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform)


def format_device_tree_values(
    device: DeviceInfo,
    name_mapping: Dict[str, str],
) -> Tuple[str, str, str, str]:
    return (
        get_device_display_name(device.device_id, name_mapping),
        format_platform_label(device.platform),
        device.status,
        device.device_id,
    )


def format_device_summary(devices: Sequence[DeviceInfo]) -> str:
    if not devices:
        return "未检测到设备"
    android_count = sum(1 for device in devices if device.platform == "android")
    harmony_count = sum(1 for device in devices if device.platform == "harmony")
    return f"总计 {len(devices)} 台 · Android {android_count} 台 · Harmony {harmony_count} 台"


def format_selected_device_summary(
    selected_device_ids: Iterable[str],
    devices: Sequence[DeviceInfo],
    name_mapping: Dict[str, str],
) -> str:
    connected_device_ids = {device.device_id for device in devices}
    selected_connected_ids = [
        device_id for device_id in selected_device_ids if device_id in connected_device_ids
    ]
    if not selected_connected_ids:
        return "未选择设备"
    labels = format_device_ids_for_log(selected_connected_ids, name_mapping)
    return f"已选 {len(selected_connected_ids)} 台：{labels}"


def format_package_summary(apk_path: Optional[Path], hap_path: Optional[Path]) -> str:
    parts = []
    if apk_path:
        parts.append(f"APK {apk_path.name}")
    if hap_path:
        parts.append(f"HAP {hap_path.name}")
    if not parts:
        return "未找到可安装包"
    return " · ".join(parts)
