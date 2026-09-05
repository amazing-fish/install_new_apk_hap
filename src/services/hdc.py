"""Resolve one HDC executable for every Harmony operation."""
import os
import shutil
from pathlib import Path


class HdcError(RuntimeError):
    """HDC configuration or execution failed, rather than an empty device list."""


def _executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _configured_path(value: str) -> Path:
    return Path(os.path.expandvars(value.strip().strip('"'))).expanduser()


def resolve_hdc_executable() -> str:
    """Explicit file/directory, SDK root, PATH, then standard Windows SDK locations.

    Invalid explicit configuration fails immediately. Resolution is not cached;
    multi-command operations keep the resolved path for their own lifetime.
    """
    name = 'hdc.exe' if os.name == 'nt' else 'hdc'
    for variable in ('HDC_EXECUTABLE', 'HDC_PATH'):
        value = os.environ.get(variable, '').strip()
        if value:
            path = _configured_path(value)
            if variable == 'HDC_PATH' and path.is_dir():
                path /= name
            if not _executable(path):
                raise HdcError(f'{variable} 指定的 HDC 不存在或不可执行：{path}')
            return str(path.resolve())

    sdk = os.environ.get('DEVECO_SDK_HOME', '').strip()
    if sdk:
        root = _configured_path(sdk)
        for relative in ('default/openharmony/toolchains', 'openharmony/toolchains', 'toolchains'):
            path = root / relative / name
            if _executable(path):
                return str(path.resolve())
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
                path = Path(root) / relative / name
                if _executable(path):
                    return str(path.resolve())
    raise HdcError('未找到 HDC；请设置 HDC_EXECUTABLE 为完整可执行文件路径，或将 toolchains 加入 PATH')
