import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services.package_scanner import find_latest_packages


def create_package(directory: Path, name: str, modified_time: int) -> Path:
    package_path = directory / name
    package_path.touch()
    os.utime(package_path, (modified_time, modified_time))
    return package_path


def test_find_latest_packages_returns_all_candidates_newest_first(tmp_path: Path) -> None:
    for index in range(8):
        create_package(tmp_path, f"android-{index}.apk", 1000 + index)
    for index in range(7):
        create_package(tmp_path, f"harmony-{index}.hap", 2000 + index)

    package_info = find_latest_packages(tmp_path)

    assert [path.name for path in package_info.apk_candidates] == [
        f"android-{index}.apk" for index in reversed(range(8))
    ]
    assert [path.name for path in package_info.hap_candidates] == [
        f"harmony-{index}.hap" for index in reversed(range(7))
    ]
    assert package_info.apk_path == tmp_path / "android-7.apk"
    assert package_info.hap_path == tmp_path / "harmony-6.hap"


def test_find_latest_packages_handles_empty_directory(tmp_path: Path) -> None:
    package_info = find_latest_packages(tmp_path)

    assert package_info.apk_path is None
    assert package_info.hap_path is None
    assert package_info.apk_candidates == []
    assert package_info.hap_candidates == []
