import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG = {
    "device_names": {},
    "last_scan_dir": "",
}


def _valid_device_names(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(name, str) for key, name in value.items()
    )


FIELD_VALIDATORS = {
    "device_names": _valid_device_names,
    "last_scan_dir": lambda value: isinstance(value, str),
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
        try:
            with self._config_path.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            if not isinstance(loaded, dict):
                raise ValueError("config root must be an object")
        except (OSError, ValueError):
            # A config that cannot be read must not prevent startup. Keep the
            # original bytes beside it so nothing recoverable is lost.
            self._config = deepcopy(DEFAULT_CONFIG)
            self._backup_unreadable()
            self.save()
            return
        for key, default in DEFAULT_CONFIG.items():
            if key not in loaded or not FIELD_VALIDATORS[key](loaded[key]):
                loaded[key] = deepcopy(default)
        # Unknown legacy keys stay on disk but are not used at runtime.
        self._config = loaded

    def _backup_unreadable(self) -> None:
        backup = self._config_path.with_name(self._config_path.name + ".bak")
        if backup.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = self._config_path.with_name(f"{self._config_path.name}.{stamp}.bak")
        try:
            os.replace(self._config_path, backup)
        except OSError:
            pass

    def save(self) -> None:
        # Write a sibling temporary file and atomically replace the target, so
        # an interrupted save leaves either the old or the new config.
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=self._config_path.name + ".", suffix=".tmp", dir=self._config_path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(self._config, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self._config_path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def set_device_name(self, device_id: str, name: str) -> None:
        self._config.setdefault("device_names", {})
        self._config["device_names"][device_id] = name
        self.save()

    def set_last_scan_dir(self, path: str) -> None:
        self._config["last_scan_dir"] = path
        self.save()
