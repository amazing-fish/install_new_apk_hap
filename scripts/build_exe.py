"""Build a complete Windows x64 EXE from checked-in, pinned metadata tools."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'vendor/metadata-tools/windows-x64'
REQUIRED_FILES = {'aapt2.exe', 'restool.exe', 'AAPT2-NOTICE.txt', 'RESTOOL-NOTICE.txt'}


def verify_bundle(directory: Path) -> list[Path]:
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf8'))
    if (manifest.get('schema_version') != 1 or manifest.get('platform') != 'windows-x64'
            or set(manifest.get('files', {})) != REQUIRED_FILES):
        raise ValueError('Incomplete or unsupported metadata tools manifest')
    for name, expected in manifest['files'].items():
        path = directory / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Metadata tool file missing or SHA-256 mismatch: {name}')
    return [directory / name for name in sorted(REQUIRED_FILES | {'manifest.json'})]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    files = verify_bundle(TOOLS)
    if os.name != 'nt' or struct.calcsize('P') != 8:
        raise SystemExit('Build with 64-bit Python on Windows')
    environment = dict(os.environ)
    # Conda keeps Tcl/Tk DLLs here instead of beside _tkinter.pyd. Give
    # PyInstaller the active interpreter's dependency path, not another SDK.
    conda_bin = Path(sys.prefix) / 'Library/bin'
    if conda_bin.is_dir():
        environment['PATH'] = str(conda_bin) + os.pathsep + os.environ.get('PATH', '')
    command = [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', '--noconsole',
               '--onefile', '--noupx', '--name', 'install_new_apk_hap',
               '--specpath', str(ROOT / 'build'), '--workpath', str(ROOT / 'build/pyinstaller'),
               '--distpath', str(args.dist_dir.resolve())]
    for path in files:
        command.extend(['--add-binary' if path.suffix == '.exe' else '--add-data',
                        f'{path}{os.pathsep}package_tools'])
    subprocess.run(command + [str(ROOT / 'src/main.py')], cwd=ROOT, env=environment, check=True)


if __name__ == '__main__':
    main()
