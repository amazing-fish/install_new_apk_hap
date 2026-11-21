"""Non-GUI diagnostics for source runs and packaged Windows EXEs; no device calls."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

from infra.tools import bundled_tools_directory, diagnose_tools, resolve_metadata_tools
from metadata import read_package_label


def _read_version() -> str:
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "VERSION" if getattr(sys, "frozen", False) else None,
        Path(__file__).resolve().parents[1] / "VERSION",
    ]
    for path in candidates:
        if path and path.is_file():
            return path.read_text(encoding="utf-8").strip()
    return ""


def _web_dist_index() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", "")) / "web_dist" / "index.html"
    return Path(__file__).resolve().parent / "web_dist" / "index.html"


def run_cli(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--package-label-report", type=Path, metavar="OUTPUT_JSON")
    action.add_argument("--tool-notices", type=Path, metavar="NEW_DIRECTORY")
    action.add_argument("--env-check", type=Path, metavar="OUTPUT_JSON")
    parser.add_argument("packages", nargs="*", type=Path)
    args = parser.parse_args(arguments)

    if args.env_check:
        if args.packages:
            parser.error("--env-check takes no package paths")
        payload = {
            "tools": diagnose_tools(),
            "bundled_directory": str(bundled_tools_directory()) if bundled_tools_directory() else None,
            "version": _read_version(),
            "web_dist_ready": _web_dist_index().is_file(),
            "webview_available": importlib.util.find_spec("webview") is not None
            and (sys.platform != "win32" or importlib.util.find_spec("clr_loader") is not None),
        }
        args.env_check.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0

    bundled = bundled_tools_directory()
    if args.tool_notices:
        if args.packages or bundled is None:
            parser.error("--tool-notices requires a packaged EXE and no package paths")
        args.tool_notices.mkdir(parents=True, exist_ok=False)
        for name in ("AAPT2-NOTICE.txt", "RESTOOL-NOTICE.txt", "manifest.json"):
            shutil.copyfile(bundled / name, args.tool_notices / name)
        return 0

    if not args.packages:
        parser.error("provide at least one package path")
    output = args.package_label_report.resolve()
    is_same_file = output in {path.resolve() for path in args.packages} or (
        output.exists() and any(path.exists() and os.path.samefile(output, path) for path in args.packages)
    )
    if is_same_file:
        parser.error("the output report must not overwrite an input package")
    tools = resolve_metadata_tools()
    rows = [dict(path=str(path.resolve()), **asdict(read_package_label(path, tools))) for path in args.packages]
    hashes = {
        name: hashlib.sha256((bundled / name).read_bytes()).hexdigest()
        for name in ("aapt2.exe", "restool.exe")
        if bundled and (bundled / name).is_file()
    }
    output.write_text(
        json.dumps(
            {
                "bundled_directory": str(bundled) if bundled else None,
                "tools": asdict(tools),
                "bundled_sha256": hashes,
                "packages": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if all(row["status"] == "resolved" for row in rows) else 1
