import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config_manager import ConfigManager


def test_new_config_contains_only_active_preferences(tmp_path: Path) -> None:
    config_path = tmp_path / "app_config.json"
    manager = ConfigManager(config_path)

    assert manager.data == {
        "device_names": {},
        "last_scan_dir": "",
    }
    assert json.loads(config_path.read_text(encoding="utf-8")) == manager.data


def test_legacy_apk_t_key_does_not_affect_supported_preferences(tmp_path: Path) -> None:
    config_path = tmp_path / "app_config.json"
    config_path.write_text(json.dumps({
        "device_names": {"a": "Pixel"},
        "last_scan_dir": "packages",
        "apk_needs_t": ["legacy.apk"],
    }), encoding="utf-8")

    manager = ConfigManager(config_path)

    assert manager.data["device_names"] == {"a": "Pixel"}
    assert manager.data["last_scan_dir"] == "packages"
    # Unknown legacy keys may remain on disk, but runtime code no longer reads them.
    assert manager.data["apk_needs_t"] == ["legacy.apk"]


def test_default_config_collections_are_isolated_between_instances(tmp_path: Path) -> None:
    first = ConfigManager(tmp_path / "first.json")
    second = ConfigManager(tmp_path / "second.json")

    first.set_device_name("a", "Pixel")

    assert first.data["device_names"] == {"a": "Pixel"}
    assert second.data["device_names"] == {}


import pytest


@pytest.mark.parametrize("content", ['{"device_names": {"a": "x"', "", "[]", "\xff\xfe"])
def test_unreadable_config_is_backed_up_and_defaults_are_used(tmp_path: Path, content: str) -> None:
    config_path = tmp_path / "app_config.json"
    config_path.write_bytes(content.encode("latin-1"))

    manager = ConfigManager(config_path)

    assert manager.data == {"device_names": {}, "last_scan_dir": ""}
    assert (tmp_path / "app_config.json.bak").read_bytes() == content.encode("latin-1")
    assert json.loads(config_path.read_text(encoding="utf-8")) == manager.data


def test_existing_backup_is_not_overwritten(tmp_path: Path) -> None:
    config_path = tmp_path / "app_config.json"
    (tmp_path / "app_config.json.bak").write_text("older", encoding="utf-8")
    config_path.write_text("broken", encoding="utf-8")

    ConfigManager(config_path)

    assert (tmp_path / "app_config.json.bak").read_text(encoding="utf-8") == "older"
    stamped = [p for p in tmp_path.glob("app_config.json.*.bak")]
    assert len(stamped) == 1 and stamped[0].read_text(encoding="utf-8") == "broken"


def test_invalid_field_types_fall_back_individually(tmp_path: Path) -> None:
    config_path = tmp_path / "app_config.json"
    config_path.write_text(json.dumps({
        "device_names": ["not", "a", "mapping"],
        "last_scan_dir": "packages",
        "legacy": 1,
    }), encoding="utf-8")

    manager = ConfigManager(config_path)

    assert manager.data == {"device_names": {}, "last_scan_dir": "packages", "legacy": 1}
    assert not (tmp_path / "app_config.json.bak").exists()


def test_failed_save_keeps_previous_file_and_no_temporary(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "app_config.json"
    manager = ConfigManager(config_path)
    manager.set_device_name("a", "Pixel")
    before = config_path.read_bytes()

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(json, "dump", interrupted)
    with pytest.raises(KeyboardInterrupt):
        manager.set_device_name("b", "Mate")

    assert config_path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["app_config.json"]
