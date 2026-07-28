import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config_manager import ConfigManager


def test_set_apk_need_t_persists_add_and_remove(tmp_path: Path) -> None:
    config_path = tmp_path / "app_config.json"
    manager = ConfigManager(config_path)

    assert manager.set_apk_need_t("demo.apk", True) is True
    assert manager.set_apk_need_t("demo.apk", True) is False
    assert ConfigManager(config_path).data["apk_needs_t"] == ["demo.apk"]

    assert manager.set_apk_need_t("demo.apk", False) is True
    assert manager.set_apk_need_t("demo.apk", False) is False
    assert ConfigManager(config_path).data["apk_needs_t"] == []


def test_default_config_collections_are_isolated_between_instances(tmp_path: Path) -> None:
    first = ConfigManager(tmp_path / "first.json")
    second = ConfigManager(tmp_path / "second.json")

    first.set_apk_need_t("first.apk", True)

    assert first.data["apk_needs_t"] == ["first.apk"]
    assert second.data["apk_needs_t"] == []
