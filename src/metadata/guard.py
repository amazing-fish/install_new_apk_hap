"""The read boundary for untrusted packages: size, time and output limits,
ZIP directory checks and text filtering. Parsers only read through here."""
import json
import os
from pathlib import Path
import re
import struct
import unicodedata
import zipfile

from infra import process
from metadata.model import PackageLabel


MAX_METADATA_BYTES = 1024 * 1024
MAX_TOOL_OUTPUT = 4 * 1024 * 1024
TOOL_TIMEOUT = 5.0
MAX_RESOURCE_BYTES = 32 * 1024 * 1024


class MetadataReadError(ValueError):
    pass


class MetadataToolError(ValueError):
    """The SDK rejected the package; this does not prove corrupt metadata."""


def run_tool(command: list[str]) -> str:
    """Keep SDK time and captured output bounded, and hide Windows consoles."""
    result = process.run(
        command, timeout=TOOL_TIMEOUT, output_limit=MAX_TOOL_OUTPUT,
        merge_stderr=True, encoding='utf-8', errors='strict', universal_newlines=False,
    )
    if result.timed_out or result.output_exceeded:
        raise MetadataReadError('tool limit exceeded')
    if result.returncode:
        raise MetadataToolError('tool failed')
    return result.stdout


def check_zip_directory(path: Path) -> None:
    # ZipFile loads the central directory eagerly. Reject huge/ZIP64 directories
    # before constructing it; large application payloads can still be read.
    with path.open('rb') as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        # Maximum comment + classic EOCD + the preceding ZIP64 locator.
        tail_size = 65535 + 22 + 20
        stream.seek(max(0, size - tail_size))
        tail = stream.read(tail_size)
    offset = tail.rfind(b'PK\x05\x06')
    if offset < 0 or offset + 22 > len(tail):
        raise zipfile.BadZipFile('missing ZIP directory')
    # ZipFile prefers the ZIP64 locator immediately before EOCD, even if the
    # legacy count/size do not use ZIP64 sentinels. Do not validate one directory
    # and then let ZipFile read a different, unbounded one.
    if offset >= 20 and tail[offset - 20:offset - 16] == b'PK\x06\x07':
        raise MetadataReadError('ZIP64 directory is unsupported')
    _, disk, start_disk, count_disk, count, length, _, comment = struct.unpack_from('<4s4H2IH', tail, offset)
    if offset + 22 + comment != len(tail) or disk or start_disk or count_disk != count:
        raise zipfile.BadZipFile('unsupported ZIP directory')
    if count == 65535 or length > MAX_METADATA_BYTES:
        raise MetadataReadError('ZIP directory limit exceeded')
    # Each classic directory entry occupies at least 46 bytes. The byte budget
    # already bounds allocations; a separate 10,000-entry cap rejects ordinary
    # APKs even when their directory is well below that budget.
    if count > length // 46:
        raise zipfile.BadZipFile('ZIP entry count exceeds directory size')


def read_json(archive: zipfile.ZipFile, member: str) -> dict:
    info = archive.getinfo(member)
    if info.file_size > MAX_METADATA_BYTES:
        raise MetadataReadError('metadata limit exceeded')
    with archive.open(info) as stream:
        content = stream.read(MAX_METADATA_BYTES + 1)
    if len(content) > MAX_METADATA_BYTES:
        raise MetadataReadError('metadata limit exceeded')
    value = json.loads(content.decode('utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('metadata must be an object')
    return value


def literal(value: object, source: str, *, references: bool = False) -> PackageLabel:
    if not isinstance(value, str) or not value.strip():
        return PackageLabel(source=source)
    text = value.strip()
    if references and re.match(r'^\$[A-Za-z_][A-Za-z_0-9]*:', text):
        return PackageLabel(status='unresolved', source=source)
    # Untrusted text must not introduce control characters or a huge UI label.
    if len(text) > 200 or any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs', 'Zl', 'Zp') for c in text):
        return PackageLabel(status='invalid', source=source)
    return PackageLabel(text, 'resolved', source)


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if len(text) > 200 or any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs', 'Zl', 'Zp') for c in text):
        return None
    return text


def _version_code(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and re.fullmatch(r'\d+', value.strip()):
        return int(value.strip())
    return None


def with_metadata(
    label: PackageLabel,
    package_name: object = None,
    version_name: object = None,
    version_code: object = None,
    test_only: bool | None = None,
) -> PackageLabel:
    return PackageLabel(
        label.name,
        label.status,
        label.source,
        _metadata_text(package_name),
        _metadata_text(version_name),
        _version_code(version_code),
        test_only,
    )
