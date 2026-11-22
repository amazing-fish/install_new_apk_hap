"""Build a standalone Windows x64 EXE: compiles React frontend, verifies pinned metadata tools, bundles with PyInstaller."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
WEB_DIST = ROOT / "backend" / "web_dist"
APP_ICON = ROOT / "backend" / "assets" / "app_icon.ico"
TOOLS = ROOT / "vendor" / "metadata-tools" / "windows-x64"
REQUIRED_FILES = {"aapt2.exe", "restool.exe", "AAPT2-NOTICE.txt", "RESTOOL-NOTICE.txt"}

EXCLUDED_MODULES = [
    "tkinter",
    "_tkinter",
    "unittest",
    "pydoc",
    "doctest",
    "test",
    "xmlrpc",
    "pdb",
    "bdb",
    "turtle",
    "turtledemo",
    "ensurepip",
    "venv",
    "pip",
    "setuptools",
    "pkg_resources",
    "distutils",
    "sqlite3",
    "_sqlite3",
    "cryptography",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "qtpy",
    "gi",
    "wx",
    "cefpython3",
    "webview.platforms.qt",
    "webview.platforms.gtk",
    "webview.platforms.cocoa",
    "webview.platforms.android",
    "webview.platforms.cef",
    "webview.platforms.mshtml",
]


def verify_bundle(directory: Path) -> list[Path]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != 1
        or manifest.get("platform") != "windows-x64"
        or set(manifest.get("files", {})) != REQUIRED_FILES
    ):
        raise ValueError("Incomplete or unsupported metadata tools manifest")
    for name, expected in manifest["files"].items():
        path = directory / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Metadata tool file missing or SHA-256 mismatch: {name}")
    return [directory / name for name in sorted(REQUIRED_FILES | {"manifest.json"})]


def create_package_tools_archive(files: list[Path], output_zip: Path) -> Path:
    """Pack verified metadata tools into a compressed archive for lazy first-run extraction."""
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(files, key=lambda p: p.name):
            info = zipfile.ZipInfo(path.name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return output_zip


def generate_pyinstaller_spec(
    *,
    spec_path: Path,
    tools_archive: Path,
    icon_path: Path,
) -> Path:
    """Write a trimmed PyInstaller onefile spec keeping WebView2 runtime loaders intact."""
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    datas = [
        (str(WEB_DIST), "web_dist"),
        (str(ROOT / "VERSION"), "."),
        (str(tools_archive), "."),
    ]
    if icon_path.is_file():
        datas.append((str(icon_path), "assets"))

    icon_repr = repr(str(icon_path)) if icon_path.is_file() else "None"
    spec_text = f"""# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    [{repr(str(ROOT / 'backend' / 'main.py'))}],
    pathex=[{repr(str(ROOT / 'backend'))}],
    binaries=[],
    datas={repr(datas)},
    hiddenimports=[],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={repr(EXCLUDED_MODULES)},
    noarchive=False,
    optimize=1,
)

def _keep_entry(entry):
    dest = entry[0].replace('\\\\', '/').lower()
    if dest.endswith('webbrowserinterop.x86.dll') or dest.endswith('webbrowserinterop.x64.dll'):
        return False
    if dest.endswith('pywebview-android.jar') or dest.endswith('/js/lib/polyfill.js'):
        return False
    return True

a.datas = [e for e in a.datas if _keep_entry(e)]
a.binaries = [e for e in a.binaries if _keep_entry(e)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [('O', None, 'OPTION')],
    name='install_new_apk_hap',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon={icon_repr},
)
"""
    spec_path.write_text(spec_text, encoding="utf-8")
    return spec_path


def build_frontend() -> None:
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise SystemExit("npm not found on PATH; cannot build frontend")
    if not (FRONTEND / "node_modules").is_dir():
        subprocess.run([npm, "ci"], cwd=FRONTEND, check=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)
    if not (WEB_DIST / "index.html").is_file():
        raise SystemExit(f"Frontend build did not produce {WEB_DIST / 'index.html'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--skip-frontend", action="store_true", help="Reuse existing backend/web_dist")
    args = parser.parse_args()

    files = verify_bundle(TOOLS)
    if os.name != "nt" or struct.calcsize("P") != 8:
        raise SystemExit("Build with 64-bit Python on Windows")

    if not args.skip_frontend:
        build_frontend()
    elif not (WEB_DIST / "index.html").is_file():
        raise SystemExit(f"--skip-frontend specified but {WEB_DIST / 'index.html'} is missing")

    tools_archive = create_package_tools_archive(files, ROOT / "build" / "package_tools.zip")
    spec_path = generate_pyinstaller_spec(
        spec_path=ROOT / "build" / "install_new_apk_hap.spec",
        tools_archive=tools_archive,
        icon_path=APP_ICON,
    )
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        "--distpath",
        str(args.dist_dir.resolve()),
        str(spec_path),
    ]
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
