"""APK: name, package, version and testOnly from one `aapt2 dump badging`."""
from pathlib import Path
import re
import zipfile

from metadata import guard
from metadata.model import PackageLabel


def _badging_package_fields(output: str) -> dict[str, str]:
    lines = [line for line in output.splitlines() if line.startswith('package: ')]
    if len(lines) != 1:
        return {}
    return {
        match.group(1): match.group(2)
        for match in re.finditer(r"([A-Za-z][A-Za-z0-9]*)='((?:\\.|[^'])*)'", lines[0])
    }


def _badging_test_only(output: str) -> bool | None:
    """AAPT2 prints testOnly only when the manifest flag is non-zero."""
    lines = [line for line in output.splitlines() if line.startswith('testOnly=')]
    if not lines:
        return False
    if len(lines) != 1:
        return None
    match = re.fullmatch(r"testOnly='(\d+)'", lines[0])
    return bool(int(match.group(1))) if match else None


def precheck(archive: zipfile.ZipFile, tool: str | None) -> PackageLabel | None:
    """A label decided by the archive alone, or None when aapt2 must run."""
    names = archive.namelist()
    if 'AndroidManifest.xml' not in names:
        return PackageLabel(source='AndroidManifest.xml')
    if archive.getinfo('AndroidManifest.xml').file_size > guard.MAX_METADATA_BYTES:
        raise guard.MetadataReadError('manifest limit exceeded')
    if 'resources.arsc' in names and archive.getinfo('resources.arsc').file_size > guard.MAX_RESOURCE_BYTES:
        raise guard.MetadataReadError('resource table limit exceeded')
    if not tool:
        return PackageLabel(status='unavailable', source='aapt2')
    return None


def read_label(path: Path, tool: str) -> PackageLabel:
    """Run once the archive is closed."""
    output = guard.run_tool([tool, 'dump', 'badging', str(path.resolve())])
    labels = [m.group(1) for line in output.splitlines()
              if (m := re.fullmatch(r"application-label:'(.*)'", line))]
    label = guard.literal(labels[0], 'aapt2:application-label:default') if len(labels) == 1 else PackageLabel(source='aapt2')
    package = _badging_package_fields(output)
    return guard.with_metadata(
        label,
        package.get('name'),
        package.get('versionName'),
        package.get('versionCode'),
        _badging_test_only(output),
    )
