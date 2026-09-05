import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import zipfile

import pytest

from services import package_metadata as metadata
from services.package_metadata import MetadataTools, PackageLabel, package_display_labels, read_package_label


FIXTURES = Path(__file__).parent / 'fixtures/package_labels'


def hap(tmp_path, document, member='module.json'):
    path = tmp_path / 'demo.hap'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(member, json.dumps(document, ensure_ascii=False))
        archive.writestr('resources.index', b'fixture: dump output is supplied by each test')
    return path


@pytest.mark.parametrize('suffix,output,tools', [
    ('hap', 'restool-dump.json', MetadataTools(restool='SDK/restool')),
    ('apk', 'aapt2-badging.txt', MetadataTools(aapt2='SDK/aapt2')),
])
def test_sdk_compiled_resource_fixtures(monkeypatch, suffix, output, tools):
    commands = []
    def run(command):
        commands.append(command)
        return (FIXTURES / output).read_bytes().decode('utf8')
    monkeypatch.setattr(metadata, '_run_tool', run)
    path = FIXTURES / f'compiled.{suffix}'
    result = read_package_label(path, tools)
    assert result.name == 'Demo 默认名称' and result.status == 'resolved'
    assert commands == [[tools.restool, 'dump', str(path.resolve())] if suffix == 'hap'
                        else [tools.aapt2, 'dump', 'badging', str(path.resolve())]]


@pytest.mark.parametrize('name', ['@Home', '$Launch', "Sam\'s Tool"])
def test_resolved_aapt_label_is_text_not_a_resource_reference(monkeypatch, name):
    monkeypatch.setattr(metadata, '_run_tool', lambda command: f"application-label:'{name}'\r\n")
    result = read_package_label(FIXTURES/'compiled.apk', MetadataTools(aapt2='aapt2'))
    assert result.name == name and result.status == 'resolved'


@pytest.mark.parametrize('document,status,name', [
    ({'app': {'label': '测试工具'}, 'module': {'name': 'entry'}}, 'resolved', '测试工具'),
    ({'app': {'label': '@Home'}}, 'resolved', '@Home'),
    ({'app': {'label': '$Launch'}}, 'resolved', '$Launch'),
    ({'app': {'label': '$string:app_name'}, 'module': {'name': 'entry'}}, 'unavailable', None),
    ({'app': {'bundleName': 'com.demo'}, 'module': {'name': 'entry', 'label': 'Module'}}, 'missing', None),
    ({'name': 'do not guess', 'appName': 'also not a contract'}, 'missing', None),
    ({'app': {'label': '$string:missing:reference'}}, 'unresolved', None),
    ({'app': {'label': 'line\nbreak'}}, 'invalid', None),
    ({'app': []}, 'invalid', None),
    ([], 'invalid', None),
])
def test_hap_only_reads_declared_label(tmp_path, document, status, name):
    result = read_package_label(hap(tmp_path, document), MetadataTools())
    assert (result.status, result.name) == (status, name)


def test_fa_uses_exact_main_ability_not_first_name(tmp_path):
    path = hap(tmp_path, {'module': {'mainAbility': '.Main', 'abilities': [
        {'name': '.Other', 'label': 'Wrong'}, {'name': '.Main', 'label': 'Correct'},
    ]}}, 'config.json')
    assert read_package_label(path, MetadataTools()).name == 'Correct'


@pytest.mark.parametrize('entries,expected', [
    ([{'value': 'English', 'language': 'en'}, {'value': '默认'}], '默认'),
    ([{'value': '仅中文', 'language': 'zh'}], None),
    ([{'value': 'Phone', 'device': 'phone'}], None),
    ([{'value': '$string:alias'}], None),
    ([{'value': 'A'}, {'value': 'B'}], None),
])
def test_hap_default_resource_selection_is_explicit(monkeypatch, tmp_path, entries, expected):
    path = hap(tmp_path, {'app': {'label': '$string:app_name', 'labelId': 123}})
    monkeypatch.setattr(metadata, '_run_tool', lambda command: json.dumps({'resource': [
        {'id': 123, 'name': 'app_name', 'type': 'string', 'entryValues': entries},
        {'id': 456, 'name': 'other', 'type': 'string', 'entryValues': [{'value': 'Wrong'}]},
    ]}))
    result = read_package_label(path, MetadataTools(restool='restool'))
    assert result.name == expected
    assert result.status == ('resolved' if expected else 'unresolved')


def test_hap_reference_id_must_match(monkeypatch, tmp_path):
    path = hap(tmp_path, {'app': {'label': '$string:app_name', 'labelId': 999}})
    monkeypatch.setattr(metadata, '_run_tool', lambda command: (FIXTURES/'restool-dump.json').read_text(encoding='utf8'))
    assert read_package_label(path, MetadataTools(restool='restool')).status == 'unresolved'


def test_missing_tool_corruption_unsupported_and_size_limit(tmp_path):
    assert read_package_label(FIXTURES/'compiled.apk', MetadataTools()).status == 'unavailable'
    bad = tmp_path/'broken.apk'
    bad.write_bytes(b'not a zip')
    assert read_package_label(bad, MetadataTools()).status == 'invalid'
    path = hap(tmp_path, {'name': 'Ignored'}, 'pack.info')
    assert read_package_label(path, MetadataTools()).status == 'unsupported'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('module.json', ' ' * (metadata.MAX_METADATA_BYTES + 1))
    assert read_package_label(path, MetadataTools()).status == 'limited'


def test_rejects_duplicate_members_and_malformed_json(tmp_path):
    path = hap(tmp_path, {'app': {'label': 'First'}})
    with pytest.warns(UserWarning), zipfile.ZipFile(path, 'a') as archive:
        archive.writestr('module.json', '{broken')
    assert read_package_label(path, MetadataTools()).status == 'invalid'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('module.json', '{broken')
    assert read_package_label(path, MetadataTools()).status == 'invalid'


@pytest.mark.parametrize('comment_size', [0, 65515, 65516, 65535])
def test_zip64_directory_cannot_bypass_legacy_size_check(tmp_path, monkeypatch, comment_size):
    path = hap(tmp_path, {'app': {'label': 'Should not be read'}})
    data = path.read_bytes()
    offset = data.rfind(b'PK\x05\x06')
    record = list(struct.unpack_from('<4s4H2IH', data, offset))
    size, start = record[5], record[6]
    zip64 = struct.pack('<4sQ2H2I4Q', b'PK\x06\x06', 44, 45, 45, 0, 0,
                        record[4], record[4], size, start)
    locator = struct.pack('<4sIQI', b'PK\x06\x07', 0, offset, 1)
    record[3], record[4], record[5] = 1, 1, 1
    record[7] = comment_size
    path.write_bytes(data[:offset] + zip64 + locator + struct.pack('<4s4H2IH', *record) + b'x' * comment_size)
    # Python follows ZIP64 despite the small, non-sentinel legacy values.
    with zipfile.ZipFile(path) as archive:
        assert len(archive.namelist()) == 2
    monkeypatch.setattr(metadata, 'MAX_METADATA_BYTES', size - 1)
    assert read_package_label(path, MetadataTools()).status == 'limited'


def test_classic_zip_with_maximum_comment_keeps_literal_label(tmp_path):
    path = hap(tmp_path, {'app': {'label': 'Maximum comment'}})
    with zipfile.ZipFile(path, 'a') as archive:
        archive.comment = b'x' * 65535
    assert read_package_label(path, MetadataTools()).name == 'Maximum comment'


def test_display_collision_cannot_overwrite_file_identity():
    a, b, c = Path('one.apk'), Path('two.apk'), Path('Same（one.apk）')
    result = package_display_labels([a, b, c], {a: PackageLabel('Same', 'resolved'), b: PackageLabel('Same', 'resolved')})
    assert list(result.values()) == [a, b, c]
    assert len(set(result)) == 3
    assert list(result)[-1] == 'Same（one.apk） [2]'


def test_sdk_resolver_honors_overrides_and_numeric_versions(tmp_path, monkeypatch):
    monkeypatch.setattr(metadata.shutil, 'which', lambda name: None)
    monkeypatch.setenv('RESTOOL_EXECUTABLE', str(tmp_path/'missing'))
    monkeypatch.delenv('AAPT2_EXECUTABLE', raising=False)
    monkeypatch.delenv('ANDROID_HOME', raising=False)
    monkeypatch.setenv('ANDROID_SDK_ROOT', str(tmp_path))
    name = 'aapt2.exe' if os.name == 'nt' else 'aapt2'
    for version in ('9.0.0', '10.0.0', '99.0.0-rc1'):
        path = tmp_path/'build-tools'/version/name
        path.parent.mkdir(parents=True)
        path.touch(); path.chmod(0o755)
    assert metadata.resolve_metadata_tools() == MetadataTools(str((tmp_path/'build-tools/10.0.0'/name).resolve()), None)
    monkeypatch.setenv('AAPT2_EXECUTABLE', str(tmp_path/'bad'))
    assert metadata.resolve_metadata_tools() == MetadataTools()


def test_restool_resolves_next_to_shared_hdc(tmp_path, monkeypatch, hdc_executable):
    monkeypatch.delenv('RESTOOL_EXECUTABLE', raising=False)
    monkeypatch.setenv('AAPT2_EXECUTABLE', str(tmp_path/'none'))
    monkeypatch.setattr(metadata.shutil, 'which', lambda name: None)
    path = Path(hdc_executable).with_name('restool.exe' if os.name == 'nt' else 'restool')
    path.touch(); path.chmod(0o755)
    assert metadata.resolve_metadata_tools().restool == str(path.resolve())


def test_tool_timeout_failure_and_output_limit(monkeypatch):
    monkeypatch.setattr(metadata, 'TOOL_TIMEOUT', 0.1)
    with pytest.raises(metadata.MetadataReadError):
        metadata._run_tool([sys.executable, '-c', 'import time;time.sleep(5)'])
    with pytest.raises(ValueError, match='tool failed'):
        metadata._run_tool([sys.executable, '-c', 'raise SystemExit(1)'])
    monkeypatch.setattr(metadata, 'TOOL_TIMEOUT', 5)
    monkeypatch.setattr(metadata, 'MAX_TOOL_OUTPUT', 100)
    with pytest.raises(metadata.MetadataReadError):
        metadata._run_tool([sys.executable, '-c', 'print("a"*101)'])
