"""Installable package scanning, slot state, and Android `-t` decision rules."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Dict, List, Optional

from metadata import PackageLabel
from metadata.display import package_display_labels, package_status_hint, package_version_text


# Display and install order; keys match PlatformDriver.package_kind.
PACKAGE_KINDS: Dict[str, str] = {"APK": ".apk", "HAP": ".hap"}
SUFFIX_TO_KIND: Dict[str, str] = {suffix: kind for kind, suffix in PACKAGE_KINDS.items()}


@dataclass(frozen=True)
class PackageCandidate:
    path: Path
    size_bytes: int
    mtime_ns: int

    @property
    def mtime_ms(self) -> int:
        return self.mtime_ns // 1_000_000

    @property
    def name(self) -> str:
        return self.path.name

    @classmethod
    def from_path(cls, path: Path) -> "PackageCandidate":
        try:
            st = path.stat()
            return cls(path=path, size_bytes=st.st_size, mtime_ns=st.st_mtime_ns)
        except OSError:
            return cls(path=path, size_bytes=0, mtime_ns=0)


def find_packages(directory: Path) -> Dict[str, List[PackageCandidate]]:
    """Single-pass os.scandir scan for all APK/HAP candidates, newest first."""
    buckets: Dict[str, List[PackageCandidate]] = {kind: [] for kind in PACKAGE_KINDS}
    with os.scandir(directory) as entries:
        for entry in entries:
            suffix = os.path.splitext(entry.name)[1].lower()
            kind = SUFFIX_TO_KIND.get(suffix)
            if kind is None:
                continue
            try:
                if not entry.is_file():
                    continue
                st = entry.stat()
            except OSError:
                continue
            buckets[kind].append(
                PackageCandidate(
                    path=Path(entry.path),
                    size_bytes=st.st_size,
                    mtime_ns=st.st_mtime_ns,
                )
            )
    for kind in buckets:
        buckets[kind].sort(key=lambda c: c.mtime_ns, reverse=True)
    return buckets


@dataclass
class PackageSlot:
    candidates: List[PackageCandidate] = field(default_factory=list)
    labels: Dict[Path, PackageLabel] = field(default_factory=dict)
    index: int = 0
    revision: int = 0

    @property
    def candidate_paths(self) -> List[Path]:
        return [c.path for c in self.candidates]

    @property
    def selected_candidate(self) -> Optional[PackageCandidate]:
        return self.candidates[self.index] if 0 <= self.index < len(self.candidates) else None

    @property
    def selected(self) -> Optional[Path]:
        cand = self.selected_candidate
        return cand.path if cand else None

    @property
    def selected_label(self) -> Optional[PackageLabel]:
        return self.labels.get(self.selected) if self.selected else None

    def replace(self, candidates, *, preferred_path: Optional[Path] = None) -> None:
        """Replace scanned candidates, selecting newest (or preferred_path if present).

        Accepts PackageCandidate items or plain Paths (stat'ed on demand).
        """
        self.candidates = [
            c if isinstance(c, PackageCandidate) else PackageCandidate.from_path(Path(c)) for c in candidates
        ]
        self.labels = {}
        self.index = 0
        self.revision += 1
        if preferred_path is not None:
            self.select_path(preferred_path)

    def choose(self, index: int) -> bool:
        if 0 <= index < len(self.candidates):
            self.index = index
            return True
        return False

    def select_path(self, target: Path) -> bool:
        try:
            resolved = target.resolve()
        except OSError:
            resolved = target
        for idx, cand in enumerate(self.candidates):
            try:
                if cand.path.resolve() == resolved:
                    self.index = idx
                    return True
            except OSError:
                if cand.path == target:
                    self.index = idx
                    return True
        return False

    def set_labels(self, labels: Dict[Path, PackageLabel]) -> None:
        """Replace all labels; metadata changes display text only, never the choice."""
        valid = set(self.candidate_paths)
        self.labels = {path: label for path, label in labels.items() if path in valid}

    def merge_labels(self, incoming: Dict[Path, PackageLabel]) -> None:
        """Incrementally merge parsed labels without altering the user's selected file."""
        valid = set(self.candidate_paths)
        for path, label in incoming.items():
            if path in valid:
                self.labels[path] = label

    def display_names(self) -> List[str]:
        return list(package_display_labels(self.candidate_paths, self.labels))

    def to_payload(self, kind: str) -> dict:
        display_list = self.display_names()
        items = []
        for idx, cand in enumerate(self.candidates):
            label = self.labels.get(cand.path)
            items.append(
                {
                    "index": idx,
                    "path": str(cand.path),
                    "filename": cand.path.name,
                    "sizeBytes": cand.size_bytes,
                    "mtimeMs": cand.mtime_ms,
                    "display": display_list[idx] if idx < len(display_list) else cand.path.name,
                    "labelLoaded": label is not None,
                    "appName": label.name if label else None,
                    "status": label.status if label else "loading",
                    "statusHint": package_status_hint(label) if label else "解析中…",
                    "packageName": label.package_name if label else None,
                    "versionName": label.version_name if label else None,
                    "versionCode": label.version_code if label else None,
                    "versionText": package_version_text(label) if label else "",
                    "testOnly": label.test_only if label else None,
                }
            )
        return {
            "kind": kind,
            "revision": self.revision,
            "selectedIndex": self.index if self.candidates else -1,
            "allowTest": apk_allow_test(self) if kind == "APK" else None,
            "candidates": items,
        }


def apk_allow_test(slot: PackageSlot) -> bool:
    """Default to `-t` unless parsed metadata explicitly reports `test_only is False`."""
    cand = slot.selected_candidate
    if cand is None:
        return False
    label = slot.selected_label
    if label is not None and label.test_only is False:
        if cand.mtime_ns > 0:
            try:
                st = cand.path.stat()
            except OSError:
                return True
            if (st.st_size, st.st_mtime_ns) != (cand.size_bytes, cand.mtime_ns):
                return True
        return False
    return True
