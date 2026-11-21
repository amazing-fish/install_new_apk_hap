"""Device platforms registry and concurrent device detection."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import threading
from typing import Dict, List, Optional

from platforms.android import ANDROID
from platforms.base import DeviceInfo, PlatformDriver
from platforms.harmony import HARMONY

# Probe and display order.
DRIVERS: Dict[str, PlatformDriver] = {driver.key: driver for driver in (ANDROID, HARMONY)}


def driver_for(platform: str) -> Optional[PlatformDriver]:
    return DRIVERS.get(platform)


@dataclass
class DeviceDetectionResult:
    devices: List[DeviceInfo]
    harmony_error: Optional[str] = None
    android_error: Optional[str] = None

    @property
    def errors(self) -> Dict[str, str]:
        return {
            key: error
            for key, error in (("android", self.android_error), ("harmony", self.harmony_error))
            if error
        }


def detect_devices(cancel: Optional[threading.Event] = None) -> DeviceDetectionResult:
    """Probe every platform concurrently; one failing preserves the others' devices."""
    drivers = list(DRIVERS.values())
    if len(drivers) <= 1:
        devices: List[DeviceInfo] = []
        errors: Dict[str, str] = {}
        for driver in drivers:
            try:
                devices.extend(driver.detect(cancel=cancel))
            except driver.tool_error as error:
                errors[driver.key] = str(error)
        return DeviceDetectionResult(
            devices=devices,
            harmony_error=errors.get("harmony"),
            android_error=errors.get("android"),
        )

    def _probe(driver: PlatformDriver):
        try:
            return driver.key, driver.detect(cancel=cancel), None
        except driver.tool_error as error:
            return driver.key, [], str(error)

    devices_by_key: Dict[str, List[DeviceInfo]] = {}
    errors: Dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(drivers), thread_name_prefix="device-probe") as pool:
        futures = [pool.submit(_probe, driver) for driver in drivers]
        for future in futures:
            key, found, err = future.result()
            devices_by_key[key] = found
            if err:
                errors[key] = err

    ordered_devices: List[DeviceInfo] = []
    for driver in drivers:
        ordered_devices.extend(devices_by_key.get(driver.key, []))

    return DeviceDetectionResult(
        devices=ordered_devices,
        harmony_error=errors.get("harmony"),
        android_error=errors.get("android"),
    )
