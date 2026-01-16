from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


@dataclass
class PackageInfo:
    apk_path: Optional[Path]
    hap_path: Optional[Path]


def _latest_file(directory: Path, suffix: str) -> Optional[Path]:
    candidates = [p for p in directory.glob(f"*{suffix}") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def find_latest_packages(directory: Path) -> PackageInfo:
    apk = _latest_file(directory, ".apk")
    hap = _latest_file(directory, ".hap")
    return PackageInfo(apk_path=apk, hap_path=hap)


def package_display_info(package_info: PackageInfo) -> Tuple[str, str]:
    apk_name = package_info.apk_path.name if package_info.apk_path else "未找到"
    hap_name = package_info.hap_path.name if package_info.hap_path else "未找到"
    return apk_name, hap_name
