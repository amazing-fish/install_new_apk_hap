"""Non-GUI diagnostics for the actual distributed executable; no device calls."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil

from services.package_metadata import (
    bundled_tools_directory, read_package_label, resolve_metadata_tools,
)


def run_cli(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--package-label-report', type=Path, metavar='OUTPUT_JSON')
    action.add_argument('--tool-notices', type=Path, metavar='NEW_DIRECTORY')
    parser.add_argument('packages', nargs='*', type=Path)
    args = parser.parse_args(arguments)
    bundled = bundled_tools_directory()
    if args.tool_notices:
        if args.packages or bundled is None:
            parser.error('--tool-notices requires a packaged EXE and no package paths')
        # Create a new directory so this diagnostic cannot overwrite user files.
        args.tool_notices.mkdir(parents=True, exist_ok=False)
        for name in ('AAPT2-NOTICE.txt', 'RESTOOL-NOTICE.txt', 'manifest.json'):
            shutil.copyfile(bundled / name, args.tool_notices / name)
        return 0
    if not args.packages:
        parser.error('provide at least one package path')
    output = args.package_label_report.resolve()
    if output in {path.resolve() for path in args.packages}:
        parser.error('the output report must not overwrite an input package')
    tools = resolve_metadata_tools()
    rows = [dict(path=str(path.resolve()), **asdict(read_package_label(path, tools)))
            for path in args.packages]
    # Record embedded bytes as well as labels: CI can detect missing/modified
    # tools in the final onefile EXE rather than trusting the source manifest.
    hashes = {name: hashlib.sha256((bundled / name).read_bytes()).hexdigest()
              for name in ('aapt2.exe', 'restool.exe')
              if bundled and (bundled / name).is_file()}
    output.write_text(json.dumps({
        'bundled_directory': str(bundled) if bundled else None,
        'tools': asdict(tools), 'bundled_sha256': hashes, 'packages': rows,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return 0 if all(row['status'] == 'resolved' for row in rows) else 1
