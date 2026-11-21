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


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
WEB_DIST = ROOT / "backend" / "web_dist"
TOOLS = ROOT / "vendor" / "metadata-tools" / "windows-x64"
REQUIRED_FILES = {"aapt2.exe", "restool.exe", "AAPT2-NOTICE.txt", "RESTOOL-NOTICE.txt"}


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

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--noconsole",
        "--onefile",
        "--noupx",
        "--name",
        "install_new_apk_hap",
        "--paths",
        str(ROOT / "backend"),
        "--specpath",
        str(ROOT / "build"),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        "--distpath",
        str(args.dist_dir.resolve()),
        "--add-data",
        f"{WEB_DIST}{os.pathsep}web_dist",
        "--add-data",
        f"{ROOT / 'VERSION'}{os.pathsep}.",
    ]
    for path in files:
        command.extend(
            ["--add-binary" if path.suffix == ".exe" else "--add-data", f"{path}{os.pathsep}package_tools"]
        )
    subprocess.run(command + [str(ROOT / "backend" / "main.py")], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
