import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

from scripts.build_exe import REQUIRED_FILES, TOOLS, verify_bundle
from services import package_metadata_cli as cli


def test_checked_in_bundle_has_all_pinned_tools_and_notices():
    assert {path.name for path in verify_bundle(TOOLS)} == REQUIRED_FILES | {'manifest.json'}


@pytest.mark.parametrize('fault', ['missing_tool', 'changed_bytes', 'omitted_notice'])
def test_incomplete_or_modified_tool_bundle_cannot_be_built(tmp_path, fault):
    hashes = {}
    for name in REQUIRED_FILES:
        content = name.encode()
        (tmp_path / name).write_bytes(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    if fault == 'missing_tool':
        (tmp_path / 'restool.exe').unlink()
    elif fault == 'changed_bytes':
        (tmp_path / 'aapt2.exe').write_bytes(b'wrong executable')
    else:
        del hashes['RESTOOL-NOTICE.txt']
    (tmp_path / 'manifest.json').write_text(json.dumps({
        'schema_version': 1, 'platform': 'windows-x64', 'files': hashes,
    }))
    with pytest.raises(ValueError):
        verify_bundle(tmp_path)


def test_diagnostic_reports_actual_success_and_failure_without_starting_gui(tmp_path):
    good = tmp_path / 'literal.hap'
    with zipfile.ZipFile(good, 'w') as archive:
        archive.writestr('module.json', json.dumps({'app': {'label': '诊断样例'}}))
    bad = tmp_path / 'broken.apk'
    bad.write_bytes(b'not a ZIP')
    output = tmp_path / 'report.json'
    assert cli.run_cli(['--package-label-report', str(output), str(good)]) == 0
    assert cli.run_cli(['--package-label-report', str(output), str(good), str(bad)]) == 1
    report = json.loads(output.read_text(encoding='utf8'))
    assert report['packages'][0]['name'] == '诊断样例'
    assert report['packages'][1]['status'] == 'invalid'
    assert report['packages'][1]['name'] is None


def test_diagnostic_cannot_overwrite_input_package(tmp_path):
    package = tmp_path / 'original.apk'
    package.write_bytes(b'original bytes')
    with pytest.raises(SystemExit) as error:
        cli.run_cli(['--package-label-report', str(package), str(package)])
    assert error.value.code == 2
    assert package.read_bytes() == b'original bytes'


def test_embedded_notices_are_available_without_an_sdk(monkeypatch, tmp_path):
    root = tmp_path / 'frozen'
    directory = root / 'package_tools'
    directory.mkdir(parents=True)
    names = ('AAPT2-NOTICE.txt', 'RESTOOL-NOTICE.txt', 'manifest.json')
    for name in names:
        (directory / name).write_bytes(name.encode())
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(root), raising=False)
    destination = tmp_path / 'exported notices'
    assert cli.run_cli(['--tool-notices', str(destination)]) == 0
    assert {p.name: p.read_bytes() for p in destination.iterdir()} == {
        name: name.encode() for name in names
    }
