"""Pure display formatting; device IDs and package paths remain the source of truth."""

from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple

from services.device_detector import DeviceInfo


DEVICE_DISPLAY_COLUMNS = ("name", "platform", "status", "device_id")
PLATFORM_LABELS = {"android": "Android", "harmony": "Harmony"}


def get_device_display_name(device_id: str, name_mapping: Dict[str, str]) -> str:
    name = name_mapping.get(device_id, "").strip()
    return name or device_id


def format_device_ids_for_log(device_ids: Iterable[str], name_mapping: Dict[str, str]) -> str:
    return "，".join(get_device_display_name(device_id, name_mapping) for device_id in device_ids)


def format_device_tree_values(
    device: DeviceInfo, name_mapping: Dict[str, str]
) -> Tuple[str, str, str, str]:
    # Storage order stays stable; Treeview.displaycolumns controls visual order.
    return (
        device.device_id,
        name_mapping.get(device.device_id, "").strip(),
        device.status,
        PLATFORM_LABELS.get(device.platform, device.platform),
    )


def format_device_summary(devices: Sequence[DeviceInfo]) -> str:
    if not devices:
        return "未检测到设备"
    android_count = sum(device.platform == "android" for device in devices)
    harmony_count = sum(device.platform == "harmony" for device in devices)
    return f"总计 {len(devices)} 台 · Android {android_count} 台 · Harmony {harmony_count} 台"


def format_selected_device_summary(
    selected_device_ids: Iterable[str],
    devices: Sequence[DeviceInfo],
    name_mapping: Dict[str, str],
) -> str:
    known_ids = {device.device_id for device in devices}
    selected_ids = list(dict.fromkeys(
        device_id for device_id in selected_device_ids if device_id in known_ids
    ))
    if not selected_ids:
        return "未选择设备"
    return f"已选 {len(selected_ids)} 台：{format_device_ids_for_log(selected_ids, name_mapping)}"


def format_package_summary(
    apk_path: Optional[Path], hap_path: Optional[Path],
    apk_name: Optional[str] = None, hap_name: Optional[str] = None,
) -> str:
    parts = []
    for platform, path, name in (('APK', apk_path, apk_name), ('HAP', hap_path, hap_name)):
        if path is not None:
            display = f'{name}（{path.name}）' if name else path.name
            parts.append(f'{platform} {display}')
    return " · ".join(parts) or "未找到可安装包"
