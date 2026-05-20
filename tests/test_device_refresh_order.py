import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main
from services.device_detector import DeviceInfo


def test_reorder_devices_for_refresh_moves_new_devices_to_top() -> None:
    previous_ids = {"old-android", "old-harmony"}
    devices = [
        DeviceInfo(device_id="old-android", platform="android", status="device"),
        DeviceInfo(device_id="new-harmony", platform="harmony", status="device"),
        DeviceInfo(device_id="old-harmony", platform="harmony", status="device"),
        DeviceInfo(device_id="new-android", platform="android", status="device"),
    ]

    assert hasattr(main, "reorder_devices_for_refresh")

    ordered_devices, new_ids = main.reorder_devices_for_refresh(devices, previous_ids)

    assert [device.device_id for device in ordered_devices] == [
        "new-harmony",
        "new-android",
        "old-android",
        "old-harmony",
    ]
    assert new_ids == {"new-harmony", "new-android"}


def test_build_crash_log_target_dispatches_by_device_platform() -> None:
    output_dir = Path("D:/")

    android_target = main.build_crash_log_target(
        DeviceInfo(device_id="android-device", platform="android", status="device"),
        output_dir,
    )
    harmony_target = main.build_crash_log_target(
        DeviceInfo(device_id="harmony-device", platform="harmony", status="device"),
        output_dir,
    )

    assert android_target.platform == "android"
    assert android_target.output_path == output_dir / "crash.log"
    assert harmony_target.platform == "harmony"
    assert harmony_target.output_path == output_dir
