"""Installable packages per kind: scanned candidates, their labels, the choice.

No Tk: the dropdown renders a slot and reports an index back, so display
text (which metadata may rewrite at any time) never identifies a file.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from metadata import PackageLabel
from metadata.display import package_display_labels


# Display and install order; the key is also the driver's `package_kind`.
PACKAGE_KINDS: Dict[str, str] = {"APK": ".apk", "HAP": ".hap"}


def find_packages(directory: Path) -> Dict[str, List[Path]]:
    """Every candidate of each kind, newest modification time first."""
    return {
        kind: sorted((path for path in directory.glob(f"*{suffix}") if path.is_file()),
                     key=lambda path: path.stat().st_mtime, reverse=True)
        for kind, suffix in PACKAGE_KINDS.items()
    }


@dataclass
class PackageSlot:
    candidates: List[Path] = field(default_factory=list)
    labels: Dict[Path, PackageLabel] = field(default_factory=dict)
    index: int = 0

    @property
    def selected(self) -> Optional[Path]:
        return self.candidates[self.index] if self.candidates else None

    @property
    def selected_label(self) -> Optional[PackageLabel]:
        return self.labels.get(self.selected)

    def replace(self, candidates: List[Path]) -> None:
        """A new scan: its newest candidate is chosen and old labels are dropped."""
        self.candidates, self.labels, self.index = list(candidates), {}, 0

    def choose(self, index: int) -> None:
        if 0 <= index < len(self.candidates):
            self.index = index

    def set_labels(self, labels: Dict[Path, PackageLabel]) -> None:
        """Metadata changes display text only; the choice stays on its file."""
        self.labels = {path: label for path, label in labels.items() if path in self.candidates}

    def display_names(self) -> List[str]:
        """Unique text per candidate, in candidate order."""
        return list(package_display_labels(self.candidates, self.labels))


def apk_allow_test(slot: PackageSlot) -> bool:
    """Metadata may optimize away -t, but can never be required to install."""
    if slot.selected is None:
        return False
    label = slot.selected_label
    return not (label is not None and label.test_only is False)
