"""Read application labels and package versions without guessing metadata fields."""
from __future__ import annotations

from pathlib import Path
import zipfile
import zlib

from infra.tools import MetadataTools
from metadata import apk, guard, hap
from metadata.model import PackageLabel

__all__ = ["PackageLabel", "read_package_label"]


def read_package_label(path: Path, tools: MetadataTools) -> PackageLabel:
    """All expected read failures become explicit display states, never guessed successes."""
    try:
        guard.check_zip_directory(path)
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("duplicate ZIP members")
            if path.suffix.lower() == ".hap":
                return hap.read_label(archive, path, tools.restool)
            if path.suffix.lower() != ".apk":
                return PackageLabel(status="unsupported")
            decided = apk.precheck(archive, tools.aapt2)
            if decided is not None:
                return decided
        return apk.read_label(path, tools.aapt2)
    except guard.MetadataReadError:
        return PackageLabel(status="limited")
    except guard.MetadataToolError:
        return PackageLabel(status="tool_failed", source="restool" if path.suffix.lower() == ".hap" else "aapt2")
    except (
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        UnicodeError,
        RecursionError,
        zipfile.BadZipFile,
        NotImplementedError,
        zlib.error,
    ):
        return PackageLabel(status="invalid")
