"""Resolve external tool executables with one set of rules.

An explicit override (``*_EXECUTABLE`` and friends) is authoritative: when it
is invalid the tool is reported unavailable, never silently replaced by some
other copy found later in the search order.
"""
from dataclasses import dataclass
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional


class ToolError(RuntimeError):
    """Tool configuration or execution failed, rather than an empty result."""


class AdbError(ToolError):
    pass


class HdcError(ToolError):
    pass


def executable_name(stem: str) -> str:
    return f'{stem}.exe' if os.name == 'nt' else stem


def is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def executable_or_none(path: Path) -> Optional[str]:
    return str(path.resolve()) if is_executable(path) else None


def configured_path(value: str) -> Path:
    """Environment values may be quoted and may contain %VARS% or ~."""
    return Path(os.path.expandvars(value.strip().strip('"'))).expanduser()


def resolve_adb_executable() -> str:
    """ADB_EXECUTABLE, then PATH, then Android SDK platform-tools.

    PATH comes before the SDK so an existing setup keeps using the same adb it
    used before resolution existed. ANDROID_SDK_ROOT/ANDROID_HOME are shared
    with many other tools, so an unusable SDK root is skipped rather than fatal.
    """
    name = executable_name('adb')
    value = os.environ.get('ADB_EXECUTABLE', '').strip()
    if value:
        path = configured_path(value)
        if not is_executable(path):
            raise AdbError(f'ADB_EXECUTABLE 指定的 adb 不存在或不可执行：{path}')
        return str(path.resolve())

    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())

    roots = [os.environ.get(variable, '').strip() for variable in ('ANDROID_SDK_ROOT', 'ANDROID_HOME')]
    if os.name == 'nt' and os.environ.get('LOCALAPPDATA'):
        roots.append(str(Path(os.environ['LOCALAPPDATA']) / 'Android/Sdk'))
    for root in filter(None, roots):
        found = executable_or_none(configured_path(root) / 'platform-tools' / name)
        if found:
            return found
    raise AdbError('未找到 adb；请设置 ADB_EXECUTABLE 为完整可执行文件路径，或将 platform-tools 加入 PATH')


def resolve_hdc_executable() -> str:
    """Explicit file/directory, SDK root, PATH, then standard Windows SDK locations.

    Invalid explicit configuration fails immediately. Resolution is not cached;
    multi-command operations keep the resolved path for their own lifetime.
    """
    name = executable_name('hdc')
    for variable in ('HDC_EXECUTABLE', 'HDC_PATH'):
        value = os.environ.get(variable, '').strip()
        if value:
            path = configured_path(value)
            if variable == 'HDC_PATH' and path.is_dir():
                path /= name
            if not is_executable(path):
                raise HdcError(f'{variable} 指定的 HDC 不存在或不可执行：{path}')
            return str(path.resolve())

    sdk = os.environ.get('DEVECO_SDK_HOME', '').strip()
    if sdk:
        root = configured_path(sdk)
        for relative in ('default/openharmony/toolchains', 'openharmony/toolchains', 'toolchains'):
            found = executable_or_none(root / relative / name)
            if found:
                return found
        raise HdcError(f'DEVECO_SDK_HOME 中未找到可执行的 HDC：{root}')

    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())

    if os.name == 'nt':
        for variable, relative in (
            ('LOCALAPPDATA', 'Huawei/Sdk/default/openharmony/toolchains'),
            ('APPDATA', 'Huawei/Sdk/default/openharmony/toolchains'),
            ('ProgramFiles', 'Huawei/DevEco Studio/sdk/default/openharmony/toolchains'),
            ('ProgramFiles(x86)', 'Huawei/DevEco Studio/sdk/default/openharmony/toolchains'),
        ):
            root = os.environ.get(variable)
            if root:
                found = executable_or_none(Path(root) / relative / name)
                if found:
                    return found
    raise HdcError('未找到 HDC；请设置 HDC_EXECUTABLE 为完整可执行文件路径，或将 toolchains 加入 PATH')


@dataclass(frozen=True)
class MetadataTools:
    aapt2: Optional[str] = None
    restool: Optional[str] = None


def _configured_tool(variable: str) -> Optional[str]:
    value = os.environ[variable].strip()
    return executable_or_none(configured_path(value)) if value.strip('"') else None


def bundled_tools_directory() -> Optional[Path]:
    """Only the frozen application's extraction directory is trusted as bundled."""
    root = getattr(sys, '_MEIPASS', None) if getattr(sys, 'frozen', False) else None
    return Path(root) / 'package_tools' if root else None


def _bundled_tool(name: str) -> Optional[str]:
    directory = bundled_tools_directory()
    return executable_or_none(directory / name) if directory else None


def resolve_metadata_tools() -> MetadataTools:
    """Explicit overrides, then bundled tools in EXEs or SDK discovery in source.

    Metadata is optional, so a missing or invalid tool is None rather than an
    error; an invalid override still never falls back to another copy.
    """
    suffix = '.exe' if os.name == 'nt' else ''
    if os.environ.get('AAPT2_EXECUTABLE', '').strip():
        aapt = _configured_tool('AAPT2_EXECUTABLE')
    elif getattr(sys, 'frozen', False):
        aapt = _bundled_tool('aapt2.exe')
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
                    aapt = executable_or_none(version / ('aapt2' + suffix))
                    if aapt:
                        break
    if os.environ.get('RESTOOL_EXECUTABLE', '').strip():
        restool = _configured_tool('RESTOOL_EXECUTABLE')
    elif getattr(sys, 'frozen', False):
        restool = _bundled_tool('restool.exe')
    else:
        restool = shutil.which('restool' + suffix)
        if not restool:
            try:
                restool = executable_or_none(Path(resolve_hdc_executable()).with_name('restool' + suffix))
            except (HdcError, OSError):
                pass
    return MetadataTools(aapt, restool)
