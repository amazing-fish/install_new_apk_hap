from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class PackageInfo:
    apk_path: Optional[Path]
    hap_path: Optional[Path]
    apk_candidates: List[Path]
    hap_candidates: List[Path]


def _latest_file(directory: Path, suffix: str) -> Optional[Path]:
    candidates = [p for p in directory.glob(f"*{suffix}") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _latest_files(directory: Path, suffix: str, limit: int = 5) -> List[Path]:
    candidates = [p for p in directory.glob(f"*{suffix}") if p.is_file()]
    if not candidates:
        return []
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def find_latest_packages(directory: Path) -> PackageInfo:
    apk = _latest_file(directory, ".apk")
    hap = _latest_file(directory, ".hap")
    apk_candidates = _latest_files(directory, ".apk")
    hap_candidates = _latest_files(directory, ".hap")
    return PackageInfo(
        apk_path=apk,
        hap_path=hap,
        apk_candidates=apk_candidates,
        hap_candidates=hap_candidates,
    )


def package_display_info(package_info: PackageInfo) -> Tuple[str, str]:
    apk_name = package_info.apk_path.name if package_info.apk_path else "未找到"
    hap_name = package_info.hap_path.name if package_info.hap_path else "未找到"
    return apk_name, hap_name
