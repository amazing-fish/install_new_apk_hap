"""Pure device display formatting; device IDs remain the source of truth.

Package dropdown text lives in `metadata.display`.
"""

from typing import Dict, Iterable, Sequence, Tuple

from platforms import DRIVERS, DeviceInfo


DEVICE_DISPLAY_COLUMNS = ("name", "platform", "status", "device_id")
PLATFORM_LABELS = {key: driver.label for key, driver in DRIVERS.items()}


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
    counts = " · ".join(
        f"{driver.label} {sum(device.platform == key for device in devices)} 台" for key, driver in DRIVERS.items()
    )
    return f"总计 {len(devices)} 台 · {counts}"


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
