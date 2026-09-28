"""Device platforms. Add a platform by adding a driver here; callers use DRIVERS."""
from dataclasses import dataclass
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
        return {key: error for key, error in (("android", self.android_error), ("harmony", self.harmony_error)) if error}


def detect_devices() -> DeviceDetectionResult:
    """Probe every platform independently; one failing keeps the others' devices."""
    devices: List[DeviceInfo] = []
    errors: Dict[str, str] = {}
    for driver in DRIVERS.values():
        try:
            devices += driver.detect()
        except driver.tool_error as error:
            errors[driver.key] = str(error)
    return DeviceDetectionResult(devices, harmony_error=errors.get("harmony"), android_error=errors.get("android"))
