import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG = {
    "device_names": {},
    "last_scan_dir": "",
    "apk_needs_t": [],
}


class ConfigManager:
    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._config = deepcopy(DEFAULT_CONFIG)
        self.load()

    @property
    def data(self) -> Dict[str, Any]:
        return self._config

    def load(self) -> None:
        if not self._config_path.exists():
            self.save()
            return
        with self._config_path.open("r", encoding="utf-8") as file:
            self._config = json.load(file)
        for key, value in DEFAULT_CONFIG.items():
            self._config.setdefault(key, deepcopy(value))

    def save(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with self._config_path.open("w", encoding="utf-8") as file:
            json.dump(self._config, file, ensure_ascii=False, indent=2)

    def set_device_name(self, device_id: str, name: str) -> None:
        self._config.setdefault("device_names", {})
        self._config["device_names"][device_id] = name
        self.save()

    def set_last_scan_dir(self, path: str) -> None:
        self._config["last_scan_dir"] = path
        self.save()

    def add_apk_need_t(self, apk_name: str) -> None:
        self.set_apk_need_t(apk_name, True)

    def set_apk_need_t(self, apk_name: str, needs_t: bool) -> bool:
        self._config.setdefault("apk_needs_t", [])
        apk_needs_t = self._config["apk_needs_t"]
        changed = False
        if needs_t and apk_name not in apk_needs_t:
            apk_needs_t.append(apk_name)
            changed = True
        elif not needs_t and apk_name in apk_needs_t:
            self._config["apk_needs_t"] = [
                remembered_name for remembered_name in apk_needs_t if remembered_name != apk_name
            ]
            changed = True
        if changed:
            self.save()
        return changed
