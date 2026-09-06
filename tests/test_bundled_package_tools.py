import sys

import pytest

from services import package_metadata as metadata
from services.package_metadata import MetadataTools


@pytest.fixture
def bundled_tools(monkeypatch, tmp_path):
    root = tmp_path / 'onefile extraction'
    folder = root / 'package_tools'
    folder.mkdir(parents=True)
    for name in ('aapt2.exe', 'restool.exe'):
        (folder / name).touch()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(root), raising=False)
    for name in ('AAPT2_EXECUTABLE', 'RESTOOL_EXECUTABLE'):
        monkeypatch.delenv(name, raising=False)
    return folder


@pytest.mark.parametrize('host_sdk', [False, True])
def test_onefile_uses_its_tools_without_requiring_or_selecting_host_sdk(
    monkeypatch, bundled_tools, tmp_path, host_sdk,
):
    old_tool = tmp_path / 'old-sdk.exe'
    old_tool.touch()
    monkeypatch.setattr(metadata.shutil, 'which', lambda name: str(old_tool) if host_sdk else None)
    monkeypatch.setattr(metadata, 'resolve_hdc_executable', lambda: str(old_tool))
    monkeypatch.setenv('ANDROID_SDK_ROOT', str(tmp_path / 'absent-sdk'))
    monkeypatch.delenv('ANDROID_HOME', raising=False)
    assert metadata.resolve_metadata_tools() == MetadataTools(
        str(bundled_tools / 'aapt2.exe'), str(bundled_tools / 'restool.exe'),
    )


def test_explicit_override_is_respected_and_invalid_override_does_not_fall_back(
    monkeypatch, bundled_tools, tmp_path,
):
    override = tmp_path / 'explicit-aapt2.exe'
    override.touch()
    monkeypatch.setenv('AAPT2_EXECUTABLE', str(override))
    monkeypatch.setenv('RESTOOL_EXECUTABLE', str(tmp_path / 'absent.exe'))
    assert metadata.resolve_metadata_tools() == MetadataTools(str(override), None)


def test_missing_onefile_tool_does_not_hide_packaging_failure_with_host_sdk(
    monkeypatch, bundled_tools, tmp_path,
):
    (bundled_tools / 'restool.exe').unlink()
    old_tool = tmp_path / 'restool.exe'
    old_tool.touch()
    monkeypatch.setattr(metadata.shutil, 'which', lambda name: str(old_tool))
    monkeypatch.setattr(metadata, 'resolve_hdc_executable', lambda: str(old_tool))
    assert metadata.resolve_metadata_tools() == MetadataTools(str(bundled_tools / 'aapt2.exe'), None)
