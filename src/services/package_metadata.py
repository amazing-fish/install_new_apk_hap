"""Read application labels; never infer a label from arbitrary name fields.

Only trusted SDK executables are invoked, never files from inside a package.
Resource labels use the package's default configuration, not the device locale.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import time
import zipfile
import zlib

from services.hdc import HdcError, resolve_hdc_executable


MAX_METADATA_BYTES = 1024 * 1024
MAX_TOOL_OUTPUT = 4 * 1024 * 1024
TOOL_TIMEOUT = 5.0
MAX_RESOURCE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class PackageLabel:
    name: str | None = None
    status: str = "missing"
    source: str = ""


@dataclass(frozen=True)
class MetadataTools:
    aapt2: str | None = None
    restool: str | None = None


def _executable(path: Path) -> str | None:
    return str(path.resolve()) if path.is_file() and os.access(path, os.X_OK) else None


def _configured_tool(variable: str) -> str | None:
    value = os.environ[variable].strip().strip('"')
    return _executable(Path(os.path.expandvars(value)).expanduser()) if value else None


def resolve_metadata_tools() -> MetadataTools:
    """Resolve once per scan. Invalid explicit overrides do not fall back."""
    suffix = '.exe' if os.name == 'nt' else ''
    if os.environ.get('AAPT2_EXECUTABLE', '').strip():
        aapt = _configured_tool('AAPT2_EXECUTABLE')
    else:
        aapt = shutil.which('aapt2' + suffix)
        for variable in ('ANDROID_SDK_ROOT', 'ANDROID_HOME'):
            if aapt:
                break
            root = os.environ.get(variable, '').strip()
            if root:
                directory = Path(os.path.expandvars(root.strip('"'))).expanduser() / 'build-tools'
                # Stable numeric SDK versions only, newest first.
                versions = [p for p in directory.glob('*') if re.fullmatch(r'\d+(\.\d+)+', p.name)]
                for version in sorted(versions, key=lambda p: tuple(map(int, p.name.split('.'))), reverse=True):
                    aapt = _executable(version / ('aapt2' + suffix))
                    if aapt:
                        break
    if os.environ.get('RESTOOL_EXECUTABLE', '').strip():
        restool = _configured_tool('RESTOOL_EXECUTABLE')
    else:
        restool = shutil.which('restool' + suffix)
        if not restool:
            try:
                restool = _executable(Path(resolve_hdc_executable()).with_name('restool' + suffix))
            except (HdcError, OSError):
                pass
    return MetadataTools(aapt, restool)


class MetadataReadError(ValueError):
    pass


def _run_tool(command: list[str]) -> str:
    """Keep SDK time and captured output bounded, and hide Windows consoles."""
    with tempfile.TemporaryFile() as output:
        with subprocess.Popen(
            command, stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        ) as process:
            deadline = time.monotonic() + TOOL_TIMEOUT
            try:
                while process.poll() is None:
                    if time.monotonic() >= deadline or os.fstat(output.fileno()).st_size > MAX_TOOL_OUTPUT:
                        raise MetadataReadError('tool limit exceeded')
                    time.sleep(0.02)
                if os.fstat(output.fileno()).st_size > MAX_TOOL_OUTPUT:
                    raise MetadataReadError('tool output limit exceeded')
                if process.returncode:
                    raise ValueError('tool failed')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        output.seek(0)
        return output.read(MAX_TOOL_OUTPUT + 1).decode('utf-8', errors='strict')


def _check_zip_directory(path: Path) -> None:
    # ZipFile loads the central directory eagerly. Reject huge/ZIP64 directories
    # before constructing it; large application payloads can still be read.
    with path.open('rb') as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - 65557))
        tail = stream.read(65557)
    offset = tail.rfind(b'PK\x05\x06')
    if offset < 0 or offset + 22 > len(tail):
        raise zipfile.BadZipFile('missing ZIP directory')
    _, disk, start_disk, count_disk, count, length, _, comment = struct.unpack_from('<4s4H2IH', tail, offset)
    if offset + 22 + comment != len(tail) or disk or start_disk or count_disk != count:
        raise zipfile.BadZipFile('unsupported ZIP directory')
    if count == 65535 or count > 10000 or length > MAX_METADATA_BYTES:
        raise MetadataReadError('ZIP directory limit exceeded')


def _read_json(archive: zipfile.ZipFile, member: str) -> dict:
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


def _literal(value: object, source: str) -> PackageLabel:
    if not isinstance(value, str) or not value.strip():
        return PackageLabel(source=source)
    text = value.strip()
    if text.startswith(('$', '@')):
        return PackageLabel(status='unresolved', source=source)
    # Untrusted text must not introduce control characters or a huge UI label.
    if len(text) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in text):
        return PackageLabel(status='invalid', source=source)
    return PackageLabel(text, 'resolved', source)


def _hap_label(archive: zipfile.ZipFile, path: Path, tool: str | None) -> PackageLabel:
    names = archive.namelist()
    if 'module.json' in names:
        document = _read_json(archive, 'module.json')
        app = document.get('app', {})
        if not isinstance(app, dict):
            raise ValueError('app must be an object')
        value, resource_id, source = app.get('label'), app.get('labelId'), 'module.json:app.label'
    elif 'config.json' in names:
        document = _read_json(archive, 'config.json')
        module = document.get('module', {})
        if not isinstance(module, dict):
            raise ValueError('module must be an object')
        # FA's visible label belongs to its declared main ability.
        main = module.get('mainAbility')
        abilities = module.get('abilities', [])
        if not isinstance(abilities, list):
            raise ValueError('abilities must be an array')
        matches = [a for a in abilities if isinstance(a, dict) and main and a.get('name') == main]
        if len(matches) != 1:
            return PackageLabel(source='config.json:module.mainAbility')
        value, resource_id = matches[0].get('label'), matches[0].get('labelId')
        source = 'config.json:module.mainAbility.label'
    else:
        return PackageLabel(status='unsupported', source='HAP metadata')
    label = _literal(value, source)
    if label.status != 'unresolved':
        return label
    if not isinstance(value, str) or not re.fullmatch(r'\$string:[A-Za-z_][A-Za-z_0-9]*', value):
        return label
    if not tool:
        return PackageLabel(status='unavailable', source='restool')
    if 'resources.index' not in names:
        return label
    if archive.getinfo('resources.index').file_size > MAX_RESOURCE_BYTES:
        raise MetadataReadError('resource table limit exceeded')
    document = json.loads(_run_tool([tool, 'dump', str(path.resolve())]))
    resources = document.get('resource', []) if isinstance(document, dict) else []
    if not isinstance(resources, list):
        raise ValueError('resources must be an array')
    matches = [r for r in resources if isinstance(r, dict) and r.get('type') == 'string'
               and r.get('name') == value.split(':', 1)[1]
               and (resource_id is None or r.get('id') == resource_id)]
    if len(matches) != 1:
        return label
    entries = matches[0].get('entryValues', [])
    if not isinstance(entries, list):
        raise ValueError('entryValues must be an array')
    # A default string has no language/region/device/other qualifiers.
    defaults = [e['value'] for e in entries if isinstance(e, dict) and set(e) == {'value'}]
    return _literal(defaults[0], source + '+restool:default') if len(defaults) == 1 else label


def read_package_label(path: Path, tools: MetadataTools) -> PackageLabel:
    """All expected read failures are display states, never guessed successes."""
    try:
        _check_zip_directory(path)
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError('duplicate ZIP members')
            if path.suffix.lower() == '.hap':
                return _hap_label(archive, path, tools.restool)
            if path.suffix.lower() != '.apk':
                return PackageLabel(status='unsupported')
            if 'AndroidManifest.xml' not in names:
                return PackageLabel(source='AndroidManifest.xml')
            if archive.getinfo('AndroidManifest.xml').file_size > MAX_METADATA_BYTES:
                raise MetadataReadError('manifest limit exceeded')
            if 'resources.arsc' in names and archive.getinfo('resources.arsc').file_size > MAX_RESOURCE_BYTES:
                raise MetadataReadError('resource table limit exceeded')
            if not tools.aapt2:
                return PackageLabel(status='unavailable', source='aapt2')
        output = _run_tool([tools.aapt2, 'dump', 'badging', str(path.resolve())])
        labels = [m.group(1) for line in output.splitlines()
                  if (m := re.fullmatch(r"application-label:'(.*)'", line))]
        return _literal(labels[0], 'aapt2:application-label:default') if len(labels) == 1 else PackageLabel(source='aapt2')
    except MetadataReadError:
        return PackageLabel(status='limited')
    except (OSError, ValueError, RuntimeError, KeyError, UnicodeError, RecursionError, zipfile.BadZipFile, NotImplementedError, zlib.error):
        return PackageLabel(status='invalid')


def package_display_labels(paths: list[Path], labels: dict[Path, PackageLabel]) -> dict[str, Path]:
    """Display strings are unique even if filenames imitate formatted labels."""
    result = {}
    statuses = {'unresolved': '资源名未解析', 'unavailable': '缺少解析工具',
                'invalid': '名称读取失败', 'missing': '未声明名称',
                'unsupported': '名称格式不支持', 'limited': '名称读取受限'}
    for path in paths:
        label = labels.get(path)
        if label is None:
            display = path.name
        elif label.name and label.status == 'resolved':
            display = f'{label.name}（{path.name}）'
        else:
            reason = f'缺少 {label.source}' if label.status == 'unavailable' else statuses.get(label.status, '名称未解析')
            display = f'{path.name} [{reason}]'
        unique, number = display, 2
        while unique in result:
            unique = f'{display} [{number}]'
            number += 1
        result[unique] = path
    return result
