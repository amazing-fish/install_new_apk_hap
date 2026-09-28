"""HAP: declared bundle/version/label fields; resource labels via RestoolV2."""
import json
from pathlib import Path
import re
import zipfile

from metadata import guard
from metadata.model import PackageLabel


def read_label(archive: zipfile.ZipFile, path: Path, tool: str | None) -> PackageLabel:
    names = archive.namelist()
    package_name = version_name = version_code = None
    if 'module.json' in names:
        document = guard.read_json(archive, 'module.json')
        app = document.get('app', {})
        if not isinstance(app, dict):
            raise ValueError('app must be an object')
        package_name = app.get('bundleName')
        version_name = app.get('versionName')
        version_code = app.get('versionCode')
        value, resource_id, source = app.get('label'), app.get('labelId'), 'module.json:app.label'
    elif 'config.json' in names:
        document = guard.read_json(archive, 'config.json')
        app = document.get('app', {})
        if isinstance(app, dict):
            package_name = app.get('bundleName')
            version = app.get('version', {})
            if isinstance(version, dict):
                version_name = version.get('name')
                version_code = version.get('code')
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
            return guard.with_metadata(
                PackageLabel(source='config.json:module.mainAbility'),
                package_name, version_name, version_code,
            )
        value, resource_id = matches[0].get('label'), matches[0].get('labelId')
        source = 'config.json:module.mainAbility.label'
    else:
        return PackageLabel(status='unsupported', source='HAP metadata')

    label = guard.literal(value, source, references=True)
    if label.status == 'unresolved' and isinstance(value, str) and re.fullmatch(r'\$string:[A-Za-z_][A-Za-z_0-9]*', value):
        if not tool:
            label = PackageLabel(status='unavailable', source='restool')
        elif 'resources.index' in names:
            if archive.getinfo('resources.index').file_size > guard.MAX_RESOURCE_BYTES:
                raise guard.MetadataReadError('resource table limit exceeded')
            try:
                document = json.loads(guard.run_tool([tool, 'dump', str(path.resolve())]))
                resources = document.get('resource', []) if isinstance(document, dict) else []
                if not isinstance(resources, list):
                    raise ValueError('resources must be an array')
                matches = [r for r in resources if isinstance(r, dict) and r.get('type') == 'string'
                           and r.get('name') == value.split(':', 1)[1]
                           and (resource_id is None or r.get('id') == resource_id)]
                if len(matches) == 1:
                    entries = matches[0].get('entryValues', [])
                    if not isinstance(entries, list):
                        raise ValueError('entryValues must be an array')
                    # A default string has no language/region/device/other qualifiers.
                    defaults = [e['value'] for e in entries if isinstance(e, dict) and set(e) == {'value'}]
                    if len(defaults) == 1:
                        label = guard.literal(defaults[0], source + '+restool:default', references=True)
            except guard.MetadataToolError:
                label = PackageLabel(status='tool_failed', source='restool')
            except guard.MetadataReadError:
                label = PackageLabel(status='limited')
            except (ValueError, KeyError, UnicodeError, RecursionError):
                label = PackageLabel(status='invalid')
    return guard.with_metadata(label, package_name, version_name, version_code)
