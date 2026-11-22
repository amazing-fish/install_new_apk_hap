import sys

import pytest

from infra import tools
from infra.tools import MetadataTools


def executable_fixture(path):
    path.touch()
    path.chmod(0o755)
    return path


@pytest.fixture
def bundled_tools(monkeypatch, tmp_path):
    root = tmp_path / 'onefile extraction'
    folder = root / 'package_tools'
    folder.mkdir(parents=True)
    for name in ('aapt2.exe', 'restool.exe'):
        executable_fixture(folder / name)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(root), raising=False)
    for name in ('AAPT2_EXECUTABLE', 'RESTOOL_EXECUTABLE'):
        monkeypatch.delenv(name, raising=False)
    return folder


@pytest.mark.parametrize('host_sdk', [False, True])
def test_onefile_uses_its_tools_without_requiring_or_selecting_host_sdk(
    monkeypatch, bundled_tools, tmp_path, host_sdk,
):
    old_tool = executable_fixture(tmp_path / 'old-sdk.exe')
    monkeypatch.setattr(tools.shutil, 'which', lambda name: str(old_tool) if host_sdk else None)
    monkeypatch.setattr(tools, 'resolve_hdc_executable', lambda: str(old_tool))
    monkeypatch.setenv('ANDROID_SDK_ROOT', str(tmp_path / 'absent-sdk'))
    monkeypatch.delenv('ANDROID_HOME', raising=False)
    assert tools.resolve_metadata_tools() == MetadataTools(
        str(bundled_tools / 'aapt2.exe'), str(bundled_tools / 'restool.exe'),
    )


def test_explicit_override_is_respected_and_invalid_override_does_not_fall_back(
    monkeypatch, bundled_tools, tmp_path,
):
    override = executable_fixture(tmp_path / 'explicit-aapt2.exe')
    monkeypatch.setenv('AAPT2_EXECUTABLE', str(override))
    monkeypatch.setenv('RESTOOL_EXECUTABLE', str(tmp_path / 'absent.exe'))
    assert tools.resolve_metadata_tools() == MetadataTools(str(override), None)


def test_missing_onefile_tool_does_not_hide_packaging_failure_with_host_sdk(
    monkeypatch, bundled_tools, tmp_path,
):
    (bundled_tools / 'restool.exe').unlink()
    old_tool = executable_fixture(tmp_path / 'restool.exe')
    monkeypatch.setattr(tools.shutil, 'which', lambda name: str(old_tool))
    monkeypatch.setattr(tools, 'resolve_hdc_executable', lambda: str(old_tool))
    assert tools.resolve_metadata_tools() == MetadataTools(str(bundled_tools / 'aapt2.exe'), None)


def _write_tools_zip(zip_path, *, corrupt_hash: bool = False):
    import hashlib
    import json
    import zipfile

    files_data = {
        'aapt2.exe': b'fake-aapt2-binary-payload',
        'restool.exe': b'fake-restool-binary-payload',
        'AAPT2-NOTICE.txt': b'aapt2 notice',
        'RESTOOL-NOTICE.txt': b'restool notice',
    }
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files_data.items()}
    if corrupt_hash:
        hashes['aapt2.exe'] = '0' * 64
    manifest = json.dumps({'schema_version': 1, 'platform': 'windows-x64', 'files': hashes}).encode('utf-8')
    with zipfile.ZipFile(zip_path, 'w') as archive:
        for name, data in files_data.items():
            archive.writestr(name, data)
        archive.writestr('manifest.json', manifest)
    return files_data


def test_onefile_zip_lazily_extracts_to_persistent_cache_and_reuses_fast_path(monkeypatch, tmp_path):
    meipass = tmp_path / 'mei_run1'
    meipass.mkdir()
    _write_tools_zip(meipass / 'package_tools.zip')
    cache_base = tmp_path / 'persistent_cache'
    cache_base.mkdir()

    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(meipass), raising=False)
    monkeypatch.setattr(tools, '_persistent_tools_cache_root', lambda: cache_base)
    for name in ('AAPT2_EXECUTABLE', 'RESTOOL_EXECUTABLE'):
        monkeypatch.delenv(name, raising=False)

    first = tools.bundled_tools_directory()
    assert first is not None and first.is_dir()
    assert first.parent == cache_base
    assert (first / 'aapt2.exe').is_file()
    assert (first / 'restool.exe').is_file()
    assert (first / 'manifest.json').is_file()

    # Second launch from a brand new _MEIPASS extracts zero files if cached directory matches.
    meipass2 = tmp_path / 'mei_run2'
    meipass2.mkdir()
    _write_tools_zip(meipass2 / 'package_tools.zip')
    monkeypatch.setattr(sys, '_MEIPASS', str(meipass2), raising=False)
    aapt_inode_before = (first / 'aapt2.exe').stat().st_ino
    second = tools.bundled_tools_directory()
    assert second == first
    assert (second / 'aapt2.exe').stat().st_ino == aapt_inode_before

    resolved = tools.resolve_metadata_tools()
    assert resolved == MetadataTools(str(first / 'aapt2.exe'), str(first / 'restool.exe'))

    # Corrupting a cached binary without touching manifest.json must trigger repair.
    (first / 'aapt2.exe').write_bytes(b'corrupted-nonempty-payload')
    repaired = tools.bundled_tools_directory()
    assert repaired == first
    assert (repaired / 'aapt2.exe').read_bytes() == b'fake-aapt2-binary-payload'


def test_persistent_tools_cache_root_uses_localappdata_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(tools.os, 'name', 'nt')
    local_dir = tmp_path / 'localappdata'
    monkeypatch.setenv('LOCALAPPDATA', str(local_dir))
    monkeypatch.delenv('APPDATA', raising=False)

    root = tools._persistent_tools_cache_root()
    assert root == local_dir / 'install_new_apk_hap' / 'package_tools'
    assert root.is_dir()


def test_onefile_zip_falls_back_to_temp_when_localappdata_missing(monkeypatch, tmp_path):
    meipass = tmp_path / 'mei_clean_env'
    meipass.mkdir()
    _write_tools_zip(meipass / 'package_tools.zip')
    temp_root = tmp_path / 'clean_temp'
    temp_root.mkdir()

    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(meipass), raising=False)
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    monkeypatch.delenv('APPDATA', raising=False)
    monkeypatch.setattr(tools.tempfile, 'gettempdir', lambda: str(temp_root))

    extracted = tools.bundled_tools_directory()
    assert extracted is not None and extracted.is_dir()
    assert str(temp_root) in str(extracted)
    assert (extracted / 'aapt2.exe').is_file()


def test_onefile_zip_rejects_tampered_binary_hash(monkeypatch, tmp_path):
    meipass = tmp_path / 'mei_bad'
    meipass.mkdir()
    _write_tools_zip(meipass / 'package_tools.zip', corrupt_hash=True)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(meipass), raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))

    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        tools.bundled_tools_directory()
