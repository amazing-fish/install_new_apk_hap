from dataclasses import dataclass


@dataclass(frozen=True)
class PackageLabel:
    name: str | None = None
    status: str = "missing"
    source: str = ""
    package_name: str | None = None
    version_name: str | None = None
    version_code: int | None = None
    test_only: bool | None = None
