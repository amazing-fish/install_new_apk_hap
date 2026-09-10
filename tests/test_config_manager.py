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
