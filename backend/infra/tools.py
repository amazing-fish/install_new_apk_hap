"""Resolve external tool executables (adb, hdc, aapt2, restool) with unified rules.

An explicit override (`*_EXECUTABLE` and friends) is authoritative: when invalid,
the tool is reported unavailable rather than silently replaced by another copy.
Also supports checking repository-local `vendor/metadata-tools/windows-x64/`
in source runs on Windows so local development gets offline metadata parsing too!
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Dict, Optional


class ToolError(RuntimeError):
    """Tool configuration or execution failed, rather than an empty result."""


class AdbError(ToolError):
    pass


class HdcError(ToolError):
    pass


def executable_name(stem: str) -> str:
    return f"{stem}.exe" if os.name == "nt" else stem


def is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def executable_or_none(path: Path) -> Optional[str]:
    return str(path.resolve()) if is_executable(path) else None


def configured_path(value: str) -> Path:
    """Environment values may be quoted and may contain %VARS% or ~."""
    return Path(os.path.expandvars(value.strip().strip('"'))).expanduser()


def resolve_adb_executable() -> str:
    """ADB_EXECUTABLE -> PATH -> Android SDK platform-tools."""
    name = executable_name("adb")
    value = os.environ.get("ADB_EXECUTABLE", "").strip()
    if value:
        path = configured_path(value)
        if not is_executable(path):
            raise AdbError(f"ADB_EXECUTABLE 指定的 adb 不存在或不可执行：{path}")
        return str(path.resolve())

    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())

    roots = [os.environ.get(variable, "").strip() for variable in ("ANDROID_SDK_ROOT", "ANDROID_HOME")]
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        roots.append(str(Path(os.environ["LOCALAPPDATA"]) / "Android/Sdk"))
    for root in filter(None, roots):
        found = executable_or_none(configured_path(root) / "platform-tools" / name)
        if found:
            return found
    raise AdbError("未找到 adb；请设置 ADB_EXECUTABLE 为完整可执行文件路径，或将 platform-tools 加入 PATH")


def resolve_hdc_executable() -> str:
    """Explicit file/directory -> DEVECO_SDK_HOME -> PATH -> standard Windows SDK locations."""
    name = executable_name("hdc")
    for variable in ("HDC_EXECUTABLE", "HDC_PATH"):
        value = os.environ.get(variable, "").strip()
        if value:
            path = configured_path(value)
            if variable == "HDC_PATH" and path.is_dir():
                path /= name
            if not is_executable(path):
                raise HdcError(f"{variable} 指定的 HDC 不存在或不可执行：{path}")
            return str(path.resolve())

    sdk = os.environ.get("DEVECO_SDK_HOME", "").strip()
    if sdk:
        root = configured_path(sdk)
        for relative in ("default/openharmony/toolchains", "openharmony/toolchains", "toolchains"):
            found = executable_or_none(root / relative / name)
            if found:
                return found
        raise HdcError(f"DEVECO_SDK_HOME 中未找到可执行的 HDC：{root}")

    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())

    if os.name == "nt":
        for variable, relative in (
            ("LOCALAPPDATA", "Huawei/Sdk/default/openharmony/toolchains"),
            ("APPDATA", "Huawei/Sdk/default/openharmony/toolchains"),
            ("ProgramFiles", "Huawei/DevEco Studio/sdk/default/openharmony/toolchains"),
            ("ProgramFiles(x86)", "Huawei/DevEco Studio/sdk/default/openharmony/toolchains"),
        ):
            root = os.environ.get(variable)
            if root:
                found = executable_or_none(Path(root) / relative / name)
                if found:
                    return found
    raise HdcError("未找到 HDC；请设置 HDC_EXECUTABLE 为完整可执行文件路径，或将 toolchains 加入 PATH")


@dataclass(frozen=True)
class MetadataTools:
    aapt2: Optional[str] = None
    restool: Optional[str] = None


def _configured_tool(variable: str) -> Optional[str]:
    value = os.environ[variable].strip()
    return executable_or_none(configured_path(value)) if value.strip('"') else None


_BUNDLED_TOOLS_LOCK = threading.Lock()


def _persistent_tools_cache_root() -> Path:
    """Return a writable persistent directory for lazily extracted bundled tools."""
    if os.name == "nt":
        for var in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(var, "").strip()
            if base:
                candidate = Path(base) / "install_new_apk_hap" / "package_tools"
                try:
                    candidate.mkdir(parents=True, exist_ok=True)
                    if os.access(candidate, os.W_OK):
                        return candidate
                except OSError:
                    pass
    fallback = Path(tempfile.gettempdir()) / "install_new_apk_hap_tools"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _is_extracted_tools_dir_valid(target_dir: Path, manifest_bytes: bytes, manifest: dict) -> bool:
    manifest_file = target_dir / "manifest.json"
    try:
        if not manifest_file.is_file() or manifest_file.read_bytes() != manifest_bytes:
            return False
        for name in manifest.get("files", {}):
            item = target_dir / name
            if not item.is_file() or item.stat().st_size <= 0:
                return False
        return True
    except OSError:
        return False


def _extract_bundled_tools_zip(zip_path: Path) -> Optional[Path]:
    """Lazily extract `package_tools.zip` once into persistent cache and verify SHA-256."""
    with zipfile.ZipFile(zip_path, "r") as archive:
        manifest_bytes = archive.read("manifest.json")
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        files = manifest.get("files")
        if (
            manifest.get("schema_version") != 1
            or manifest.get("platform") != "windows-x64"
            or not isinstance(files, dict)
            or not files
        ):
            raise ValueError("Invalid bundled package_tools manifest")

        allowed = set(files.keys()) | {"manifest.json"}
        for member in archive.namelist():
            if member not in allowed or "/" in member or "\\" in member or ".." in member:
                raise ValueError(f"Unexpected archive entry in package_tools.zip: {member}")

        digest = hashlib.sha256(manifest_bytes).hexdigest()[:16]
        cache_root = _persistent_tools_cache_root()
        target_dir = cache_root / digest

        if _is_extracted_tools_dir_valid(target_dir, manifest_bytes, manifest):
            return target_dir

        tmp_dir = Path(tempfile.mkdtemp(prefix=f".extract_{digest}_", dir=cache_root))
        try:
            for name, expected_hash in files.items():
                data = archive.read(name)
                if hashlib.sha256(data).hexdigest() != expected_hash:
                    raise ValueError(f"SHA-256 mismatch extracting bundled tool: {name}")
                dest = tmp_dir / name
                dest.write_bytes(data)
                if os.name != "nt":
                    dest.chmod(0o755)
            (tmp_dir / "manifest.json").write_bytes(manifest_bytes)

            if _is_extracted_tools_dir_valid(target_dir, manifest_bytes, manifest):
                return target_dir

            if target_dir.exists():
                stale_dir = Path(tempfile.mkdtemp(prefix=f".stale_{digest}_", dir=cache_root))
                shutil.rmtree(stale_dir, ignore_errors=True)
                try:
                    os.replace(target_dir, stale_dir)
                except OSError:
                    shutil.rmtree(target_dir, ignore_errors=True)
                else:
                    shutil.rmtree(stale_dir, ignore_errors=True)
            try:
                os.replace(tmp_dir, target_dir)
            except OSError:
                if _is_extracted_tools_dir_valid(target_dir, manifest_bytes, manifest):
                    return target_dir
                raise
            return target_dir
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)


def bundled_tools_directory() -> Optional[Path]:
    """Return the frozen application's package_tools directory, lazily extracting archive if needed."""
    root = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
    if not root:
        return None
    root_path = Path(root)
    direct = root_path / "package_tools"
    if direct.is_dir():
        return direct
    archive = root_path / "package_tools.zip"
    if archive.is_file():
        with _BUNDLED_TOOLS_LOCK:
            if direct.is_dir():
                return direct
            return _extract_bundled_tools_zip(archive)
    return direct


def _repo_vendor_tools_directory() -> Optional[Path]:
    """In Windows source runs, allow using checked-in vendor metadata tools as fallback."""
    if os.name != "nt":
        return None
    candidate = Path(__file__).resolve().parents[2] / "vendor" / "metadata-tools" / "windows-x64"
    return candidate if candidate.is_dir() else None


def _bundled_tool(name: str) -> Optional[str]:
    directory = bundled_tools_directory()
    return executable_or_none(directory / name) if directory else None


def _vendor_tool(name: str) -> Optional[str]:
    directory = _repo_vendor_tools_directory()
    return executable_or_none(directory / name) if directory else None


def resolve_metadata_tools() -> MetadataTools:
    """Explicit overrides -> bundled EXE tools -> PATH / SDK -> Windows repo vendor fallback."""
    suffix = ".exe" if os.name == "nt" else ""
    if os.environ.get("AAPT2_EXECUTABLE", "").strip():
        aapt = _configured_tool("AAPT2_EXECUTABLE")
    elif getattr(sys, "frozen", False):
        aapt = _bundled_tool("aapt2.exe")
    else:
        aapt = shutil.which("aapt2" + suffix)
        for variable in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
            if aapt:
                break
            root = os.environ.get(variable, "").strip()
            if root:
                directory = Path(os.path.expandvars(root.strip('"'))).expanduser() / "build-tools"
                versions = [p for p in directory.glob("*") if re.fullmatch(r"\d+(\.\d+)+", p.name)]
                for version in sorted(versions, key=lambda p: tuple(map(int, p.name.split("."))), reverse=True):
                    aapt = executable_or_none(version / ("aapt2" + suffix))
                    if aapt:
                        break
        if not aapt:
            aapt = _vendor_tool("aapt2.exe")

    if os.environ.get("RESTOOL_EXECUTABLE", "").strip():
        restool = _configured_tool("RESTOOL_EXECUTABLE")
    elif getattr(sys, "frozen", False):
        restool = _bundled_tool("restool.exe")
    else:
        restool = shutil.which("restool" + suffix)
        if not restool:
            try:
                restool = executable_or_none(Path(resolve_hdc_executable()).with_name("restool" + suffix))
            except (HdcError, OSError):
                pass
        if not restool:
            restool = _vendor_tool("restool.exe")
    return MetadataTools(aapt, restool)


def diagnose_tools() -> Dict[str, Dict[str, Optional[str] | bool]]:
    """Return structured availability and resolved path for all external tools."""
    report: Dict[str, Dict[str, Optional[str] | bool]] = {}
    try:
        adb_path = resolve_adb_executable()
        report["adb"] = {"available": True, "path": adb_path, "error": None}
    except AdbError as err:
        report["adb"] = {"available": False, "path": None, "error": str(err)}

    try:
        hdc_path = resolve_hdc_executable()
        report["hdc"] = {"available": True, "path": hdc_path, "error": None}
    except HdcError as err:
        report["hdc"] = {"available": False, "path": None, "error": str(err)}

    meta = resolve_metadata_tools()
    report["aapt2"] = {
        "available": bool(meta.aapt2),
        "path": meta.aapt2,
        "error": None if meta.aapt2 else "未找到 aapt2（APK 应用名/版本解析不可用，仍可正常安装）",
    }
    report["restool"] = {
        "available": bool(meta.restool),
        "path": meta.restool,
        "error": None if meta.restool else "未找到 restool（HAP 资源型名称解析不可用，仍可正常安装）",
    }
    return report
