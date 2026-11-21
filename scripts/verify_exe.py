"""Verify a built Windows standalone EXE in a clean environment without SDKs on PATH."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "vendor" / "metadata-tools" / "windows-x64" / "manifest.json"


def print_summary_json(summary: dict, stream=None) -> None:
    """Write summary JSON without failing on legacy Windows console encodings (e.g. cp1252)."""
    target = stream if stream is not None else sys.stdout
    try:
        target.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    except UnicodeEncodeError:
        target.write(json.dumps(summary, ensure_ascii=True, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    exe = args.exe.resolve()
    if not exe.is_file():
        raise SystemExit(f"EXE not found: {exe}")

    clean_env = {
        "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
        "PATH": os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"),
        "TEMP": tempfile.gettempdir(),
        "TMP": tempfile.gettempdir(),
    }

    with tempfile.TemporaryDirectory(prefix="verify_installer_exe_") as tmp:
        tmp_dir = Path(tmp)
        env_json = tmp_dir / "env.json"
        notices_dir = tmp_dir / "notices"
        subprocess.run([str(exe), "--env-check", str(env_json)], env=clean_env, check=True)
        subprocess.run([str(exe), "--tool-notices", str(notices_dir)], env=clean_env, check=True)

        env_report = json.loads(env_json.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for req in ("AAPT2-NOTICE.txt", "RESTOOL-NOTICE.txt", "manifest.json"):
            if not (notices_dir / req).is_file():
                raise SystemExit(f"Missing exported notice file: {req}")

        assert env_report["tools"]["aapt2"]["available"], "Bundled aapt2 not detected in isolated EXE"
        assert env_report["tools"]["restool"]["available"], "Bundled restool not detected in isolated EXE"
        expected_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        if env_report.get("web_dist_ready") is not True:
            raise SystemExit(f"Bundled frontend web_dist/index.html missing in isolated EXE: {env_report}")
        if env_report.get("webview_available") is not True:
            raise SystemExit(f"PyWebView / clr_loader runtime unavailable in isolated EXE: {env_report}")
        if env_report.get("version") != expected_version:
            raise SystemExit(
                f"Embedded VERSION mismatch in isolated EXE: expected {expected_version!r}, got {env_report.get('version')!r}"
            )

        # Exercise the bundled tools on real compiled fixtures, as v0.10 did.
        fixtures = ROOT / "tests" / "fixtures" / "package_labels"
        labels_json = tmp_dir / "labels.json"
        packages = [fixtures / "compiled.apk", fixtures / "compiled.hap", fixtures / "compiled-v2.hap"]
        subprocess.run([str(exe), "--package-label-report", str(labels_json), *map(str, packages)],
                       env=clean_env, check=True)
        labels = json.loads(labels_json.read_text(encoding="utf-8"))
        reported = labels.get("packages", [])
        expected_paths = [str(p.resolve()) for p in packages]
        actual_paths = [
            str(Path(row["path"]).resolve())
            for row in reported
            if isinstance(row, dict) and row.get("path")
        ]
        if (
            len(reported) != len(expected_paths)
            or len(set(actual_paths)) != len(expected_paths)
            or set(actual_paths) != set(expected_paths)
        ):
            raise SystemExit(
                f"Incomplete or mismatched package fixture results: expected {expected_paths}, got {reported}"
            )
        for row in reported:
            if row.get("status") != "resolved" or row.get("name") != "Demo 默认名称":
                raise SystemExit(f"Unexpected package label in isolated EXE: {row}")
        bundled_hashes = labels.get("bundled_sha256", {})
        for name in ("aapt2.exe", "restool.exe"):
            if bundled_hashes.get(name) != manifest["files"][name]:
                raise SystemExit(f"Embedded {name} hash does not match manifest")

        summary = {
            "exe": str(exe),
            "size_bytes": exe.stat().st_size,
            "version": env_report.get("version"),
            "web_dist_ready": env_report.get("web_dist_ready"),
            "webview_available": env_report.get("webview_available"),
            "bundled_directory": env_report.get("bundled_directory"),
            "manifest_files": sorted(manifest["files"].keys()),
            "tools": env_report["tools"],
            "packages": labels["packages"],
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print_summary_json(summary)


if __name__ == "__main__":
    main()
