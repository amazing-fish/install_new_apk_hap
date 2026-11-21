from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class PackageLabel:
    name: str | None = None
    status: str = "missing"
    source: str = ""
    package_name: str | None = None
    version_name: str | None = None
    version_code: int | None = None
    test_only: bool | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "PackageLabel":
        return cls(
            name=raw.get("name"),
            status=str(raw.get("status", "missing")),
            source=str(raw.get("source", "")),
            package_name=raw.get("package_name"),
            version_name=raw.get("version_name"),
            version_code=raw.get("version_code"),
            test_only=raw.get("test_only"),
        )
