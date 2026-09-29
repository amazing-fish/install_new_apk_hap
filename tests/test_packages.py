import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from metadata import PackageLabel
from packages import PackageSlot, apk_allow_test, find_packages


def create_package(directory: Path, name: str, modified_time: int) -> Path:
    package_path = directory / name
    package_path.touch()
    os.utime(package_path, (modified_time, modified_time))
    return package_path


def test_find_packages_returns_all_candidates_newest_first(tmp_path: Path) -> None:
    for index in range(8):
        create_package(tmp_path, f"android-{index}.apk", 1000 + index)
    for index in range(7):
        create_package(tmp_path, f"harmony-{index}.hap", 2000 + index)
    (tmp_path / "folder.apk").mkdir()  # only files are packages

    found = find_packages(tmp_path)

    assert list(found) == ["APK", "HAP"]
    assert [path.name for path in found["APK"]] == [f"android-{index}.apk" for index in reversed(range(8))]
    assert [path.name for path in found["HAP"]] == [f"harmony-{index}.hap" for index in reversed(range(7))]


def test_find_packages_handles_empty_directory(tmp_path: Path) -> None:
    assert find_packages(tmp_path) == {"APK": [], "HAP": []}


def test_slot_selects_by_index_and_labels_never_move_the_choice() -> None:
    old, new = Path("old.apk"), Path("new.apk")
    slot = PackageSlot()
    assert slot.selected is None and slot.display_names() == []
    slot.replace([new, old])
    assert slot.selected == new
    slot.choose(1)
    assert slot.selected == old
    slot.choose(5)  # out of range: ignored
    assert slot.selected == old
    # Both files get the same display name; the index still identifies the file.
    same = PackageLabel("同名应用", "resolved", version_name="1.0")
    slot.set_labels({new: same, old: same, Path("elsewhere.apk"): same})
    assert slot.selected == old and slot.selected_label == same
    assert set(slot.labels) == {new, old}
    assert slot.display_names() == ["同名应用 · 1.0（new.apk）", "同名应用 · 1.0（old.apk）"]
    slot.replace([old])  # a rescan chooses the newest again and drops labels
    assert (slot.selected, slot.labels) == (old, {})


@pytest.mark.parametrize("label,expected", [
    (None, True),
    (PackageLabel("Test", "resolved", test_only=True), True),
    (PackageLabel("Release", "resolved", test_only=False), False),
    (PackageLabel(status="unavailable", source="aapt2"), True),
    (PackageLabel(status="tool_failed", source="aapt2"), True),
    (PackageLabel(status="invalid"), True),
    (PackageLabel(status="limited"), True),
    (PackageLabel(status="unsupported"), True),
])
def test_apk_allow_test_only_turns_off_for_explicit_false(label, expected) -> None:
    apk = Path("demo.apk")
    slot = PackageSlot()
    slot.replace([apk])
    slot.set_labels({} if label is None else {apk: label})
    assert apk_allow_test(slot) is expected


def test_no_apk_does_not_request_t() -> None:
    assert apk_allow_test(PackageSlot()) is False
