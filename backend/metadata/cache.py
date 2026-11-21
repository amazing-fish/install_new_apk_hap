"""Persistent atomic LRU disk cache for package metadata keyed by file + tool fingerprints."""
from __future__ import annotations

from collections import OrderedDict
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Optional

from metadata.model import PackageLabel

CACHE_SCHEMA_VERSION = 1
MAX_CACHE_ENTRIES = 512
TRANSIENT_STATUSES = frozenset({"invalid", "limited", "tool_failed"})


def make_cache_key(file_fp: tuple, tool_key: tuple) -> str:
    return json.dumps([list(file_fp), [list(t) if t else None for t in tool_key]], separators=(",", ":"))


class PersistentMetadataCache:
    """Thread-safe LRU cache with optional atomic JSON persistence on disk."""

    def __init__(self, cache_path: Optional[Path] = None, max_entries: int = MAX_CACHE_ENTRIES) -> None:
        self._path = cache_path
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._entries: "OrderedDict[str, PackageLabel]" = OrderedDict()
        self._dirty = False
        if self._path is not None:
            self._load()

    def _load(self) -> None:
        if self._path is None or not self._path.is_file():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema") != CACHE_SCHEMA_VERSION:
                return
            items = payload.get("entries", [])
            if not isinstance(items, list):
                return
            with self._lock:
                for entry in items[-self._max_entries :]:
                    if isinstance(entry, list) and len(entry) == 2 and isinstance(entry[0], str) and isinstance(entry[1], dict):
                        label = PackageLabel.from_dict(entry[1])
                        if label.status not in TRANSIENT_STATUSES:
                            self._entries[entry[0]] = label
        except (OSError, ValueError, TypeError):
            pass

    def get(self, key: str) -> Optional[PackageLabel]:
        with self._lock:
            label = self._entries.get(key)
            if label is not None:
                self._entries.move_to_end(key)
            return label

    def put(self, key: str, label: PackageLabel) -> None:
        if label.status in TRANSIENT_STATUSES:
            return
        with self._lock:
            self._entries[key] = label
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
            self._dirty = True

    def flush(self) -> None:
        if self._path is None:
            return
        with self._flush_lock:
            with self._lock:
                if not self._dirty:
                    return
                snapshot = [[k, v.to_dict()] for k, v in self._entries.items()]
                self._dirty = False
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp_name = tempfile.mkstemp(
                    prefix=self._path.name + ".",
                    suffix=".tmp",
                    dir=self._path.parent,
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        json.dump({"schema": CACHE_SCHEMA_VERSION, "entries": snapshot}, handle, ensure_ascii=False)
                        handle.flush()
                    os.replace(tmp_name, self._path)
                except BaseException:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass
                    raise
            except OSError:
                pass
