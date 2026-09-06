"""Exercise the final onefile EXE after removing developer SDK dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def run_exe(command: list[str], app_dir: Path, environment: dict) -> int:
    process = subprocess.Popen(command, cwd=app_dir, env=environment)
    try:
        return process.wait(timeout=45)
    except subprocess.TimeoutExpired:
        # A onefile EXE has a bootloader parent and an application child.
        # Kill the owned tree before the parent exits, so a failed GUI startup
        # cannot leave a dialog/process behind or hold the temporary files open.
        subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/taskkill.exe'),
                        '/PID', str(process.pid), '/T', '/F'], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        process.wait(timeout=10)
        raise


def verify_exe(executable: Path, work: Path) -> dict:
    app_dir = work / 'standalone app'
    app_dir.mkdir()
    exe = app_dir / executable.name
    shutil.copyfile(executable, exe)
    assert list(app_dir.iterdir()) == [exe], 'Only the EXE may be copied'
    fixture_dir = work / 'packages'
    fixture_dir.mkdir()
    names = ('compiled.apk', 'compiled.hap', 'compiled-v2.hap')
    packages = []
    for name in names:
        path = fixture_dir / name
        shutil.copyfile(ROOT / 'tests/fixtures/package_labels' / name, path)
        packages.append(path)
    environment = dict(os.environ)
    for key in list(environment):
        if key.upper() in {'AAPT2_EXECUTABLE', 'RESTOOL_EXECUTABLE', 'ANDROID_HOME',
                           'ANDROID_SDK_ROOT', 'DEVECO_SDK_HOME', 'HDC_EXECUTABLE', 'HDC_PATH'}:
            del environment[key]
    environment['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    for key in ('APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP'):
        folder = work / ('temp' if key == 'TMP' else key.lower())
        folder.mkdir(exist_ok=True)
        environment[key] = str(folder)
    output = work / 'labels.json'
    returncode = run_exe(
        [str(exe), '--package-label-report', str(output), *map(str, packages)],
        app_dir, environment,
    )
    assert output.is_file(), f'EXE produced no diagnostic report (exit {returncode})'
    report = json.loads(output.read_text(encoding='utf8'))
    assert returncode == 0, report
    assert len(report['packages']) == len(names)
    assert [Path(row['path']).name for row in report['packages']] == list(names)
    assert all(row['status'] == 'resolved' and row['name'] == 'Demo 默认名称'
               for row in report['packages']), report
    bundled = Path(report['bundled_directory'])
    assert bundled.parent.parent == work / 'temp', bundled
    assert report['tools'] == {'aapt2': str(bundled / 'aapt2.exe'),
                               'restool': str(bundled / 'restool.exe')}
    manifest = json.loads((ROOT / 'vendor/metadata-tools/windows-x64/manifest.json').read_text())
    assert report['bundled_sha256'] == {name: manifest['files'][name]
                                        for name in ('aapt2.exe', 'restool.exe')}
    notices = work / 'exported notices'
    assert run_exe([str(exe), '--tool-notices', str(notices)], app_dir, environment) == 0
    for name in ('AAPT2-NOTICE.txt', 'RESTOOL-NOTICE.txt'):
        assert hashlib.sha256((notices / name).read_bytes()).hexdigest() == manifest['files'][name]
    assert json.loads((notices / 'manifest.json').read_text()) == manifest
    report.update(standalone_exe=True, sdk_environment_removed=True, notices_verified=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='metadata-exe-') as temp:
        result = verify_exe(args.executable.resolve(), Path(temp).resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('Standalone EXE: APK, HAP v1/v2 and bundled notices verified without SDK configuration')
