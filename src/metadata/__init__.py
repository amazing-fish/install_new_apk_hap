"""Read application labels and package versions without guessing metadata fields.

Only trusted SDK executables are invoked, never files from inside a package.
Resource labels use the package's default configuration, not the device locale.
Every read goes through `guard` (size/time/output limits and text filtering);
`apk` and `hap` hold the format rules, `display` the dropdown text, and
`loader` the single background worker.
"""
from pathlib import Path
import zipfile
import zlib

from infra.tools import MetadataTools
from metadata import apk, guard, hap
from metadata.model import PackageLabel


def read_package_label(path: Path, tools: MetadataTools) -> PackageLabel:
    """All expected read failures are display states, never guessed successes."""
    try:
        guard.check_zip_directory(path)
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError('duplicate ZIP members')
            if path.suffix.lower() == '.hap':
                return hap.read_label(archive, path, tools.restool)
            if path.suffix.lower() != '.apk':
                return PackageLabel(status='unsupported')
            decided = apk.precheck(archive, tools.aapt2)
            if decided is not None:
                return decided
        return apk.read_label(path, tools.aapt2)
    except guard.MetadataReadError:
        return PackageLabel(status='limited')
    except guard.MetadataToolError:
        return PackageLabel(status='tool_failed', source='restool' if path.suffix.lower() == '.hap' else 'aapt2')
    except (OSError, ValueError, RuntimeError, KeyError, UnicodeError, RecursionError, zipfile.BadZipFile, NotImplementedError, zlib.error):
        return PackageLabel(status='invalid')
