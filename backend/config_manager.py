"""Atomic configuration persistence with schema validation and legacy compatibility."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Dict, List


MAX_RECENT_DIRS = 8

DEFAULT_CONFIG: Dict[str, Any] = {
    "device_names": {},
    "last_scan_dir": "",
    "recent_dirs": [],
    "log_output_dir": "",
    "theme": "system",
    "parallel_install": True,
    "max_concurrency": 4,
}


def _valid_device_names(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(name, str) for key, name in value.items()
    )


def _valid_recent_dirs(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _valid_theme(value: Any) -> bool:
    return isinstance(value, str) and value in ("system", "light", "dark")


def _valid_max_concurrency(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 8


FIELD_VALIDATORS = {
    "device_names": _valid_device_names,
    "last_scan_dir": lambda value: isinstance(value, str),
    "recent_dirs": _valid_recent_dirs,
    "log_output_dir": lambda value: isinstance(value, str),
    "theme": _valid_theme,
    "parallel_install": lambda value: isinstance(value, bool),
    "max_concurrency": _valid_max_concurrency,
}


def default_log_output_dir() -> Path:
    """Windows defaults to D:\\ when available (v0.10 compatibility), else user home."""
    if os.name == "nt":
        d_drive = Path("D:/")
        if d_drive.exists():
            return d_drive
    return Path.home() / "install_new_apk_hap_logs"


class ConfigManager:
    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._lock = threading.RLock()
        self._config = deepcopy(DEFAULT_CONFIG)
        self.load()

    @property
    def path(self) -> Path:
        return self._config_path

    @property
    def data(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._config)

    def load(self) -> None:
        with self._lock:
            if not self._config_path.exists():
                self.save()
                return
            try:
                with self._config_path.open("r", encoding="utf-8") as file:
                    loaded = json.load(file)
                if not isinstance(loaded, dict):
                    raise ValueError("config root must be an object")
            except (OSError, ValueError):
                self._config = deepcopy(DEFAULT_CONFIG)
                self._backup_unreadable()
                self.save()
                return
            for key, default in DEFAULT_CONFIG.items():
                if key not in loaded or not FIELD_VALIDATORS[key](loaded[key]):
                    loaded[key] = deepcopy(default)
            # Keep unknown legacy keys intact on disk.
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
        with self._lock:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=self._config_path.name + ".",
                suffix=".tmp",
                dir=self._config_path.parent,
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
        with self._lock:
            names = self._config.setdefault("device_names", {})
            cleaned = name.strip()
            if cleaned:
                names[device_id] = cleaned
            else:
                names.pop(device_id, None)
            self.save()

    def set_last_scan_dir(self, path: str) -> None:
        cleaned = path.strip()
        with self._lock:
            self._config["last_scan_dir"] = cleaned
            if cleaned:
                recents: List[str] = [d for d in self._config.get("recent_dirs", []) if d != cleaned]
                recents.insert(0, cleaned)
                self._config["recent_dirs"] = recents[:MAX_RECENT_DIRS]
            self.save()

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            for key in ("log_output_dir", "theme", "parallel_install", "max_concurrency"):
                if key in updates and FIELD_VALIDATORS[key](updates[key]):
                    value = updates[key]
                    if key == "log_output_dir" and isinstance(value, str):
                        value = value.strip()
                    self._config[key] = value
            self.save()
            return deepcopy(self._config)

    def resolved_log_output_dir(self) -> Path:
        custom = str(self._config.get("log_output_dir", "")).strip()
        if custom:
            return Path(os.path.expandvars(custom)).expanduser()
        return default_log_output_dir()
