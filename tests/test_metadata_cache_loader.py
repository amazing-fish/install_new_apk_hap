from __future__ import annotations

import json
from pathlib import Path
import threading
import zipfile

from infra.tools import MetadataTools
from metadata import PackageLabel, read_package_label
from metadata.cache import PersistentMetadataCache
from metadata.loader import PackageLabelLoader


def _make_stage_hap(path: Path, *, name: str = "DemoApp", bundle: str = "com.example.hm", version: str = "2.0.1", code: int = 201) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "module.json",
            json.dumps(
                {
                    "app": {
                        "bundleName": bundle,
                        "versionName": version,
                        "versionCode": code,
                        "label": name,
                    }
                }
            ),
        )
    return path


def test_read_stage_hap_and_persistent_cache_loader(tmp_path: Path):
    hap1 = _make_stage_hap(tmp_path / "newest.hap", name="最新鸿蒙应用", version="3.1.0", code=310)
    hap2 = _make_stage_hap(tmp_path / "older.hap", name="旧版应用", version="3.0.0", code=300)

    lbl = read_package_label(hap1, MetadataTools())
    assert lbl.status == "resolved"
    assert lbl.name == "最新鸿蒙应用"
    assert lbl.package_name == "com.example.hm"
    assert lbl.version_name == "3.1.0"
    assert lbl.version_code == 310

    cache_file = tmp_path / "meta_cache.json"
    done_event = threading.Event()
    batches: list[tuple[dict, bool]] = []

    loader = PackageLabelLoader(post=lambda fn: fn(), cache_path=cache_file, max_workers=2)
    try:
        def on_update(_gen, labels, _fps, done):
            batches.append((dict(labels), done))
            if done:
                done_event.set()

        loader.submit([hap1, hap2], on_update, priority_paths=[hap1])
        assert done_event.wait(timeout=5.0)
        merged = {}
        for batch, _ in batches:
            merged.update(batch)
        assert merged[hap1].name == "最新鸿蒙应用"
        assert merged[hap2].name == "旧版应用"
        # Priority path must arrive in the first batch.
        assert hap1 in batches[0][0]
    finally:
        loader.close()

    # Cache file persisted on disk; second loader should serve both immediately in 1 batch!
    assert cache_file.is_file()
    cache = PersistentMetadataCache(cache_file)
    assert len(cache._entries) >= 2

    done2 = threading.Event()
    batches2: list[tuple[dict, bool]] = []
    loader2 = PackageLabelLoader(post=lambda fn: fn(), cache_path=cache_file, max_workers=2)
    try:
        def on_update2(_gen, labels, _fps, done):
            batches2.append((dict(labels), done))
            if done:
                done2.set()

        loader2.submit([hap1, hap2], on_update2, priority_paths=[hap1])
        assert done2.wait(timeout=5.0)
        assert len(batches2) == 1
        assert batches2[0][1] is True
        assert set(batches2[0][0].keys()) == {hap1, hap2}
    finally:
        loader2.close()


def test_metadata_cache_hits_across_different_onefile_tool_paths_with_same_manifest(monkeypatch, tmp_path):
    import hashlib
    from metadata import loader as loader_mod

    hap = _make_stage_hap(tmp_path / "cached.hap", name="跨重启命中应用", version="1.0.0", code=100)
    cache_file = tmp_path / "meta_cache.json"

    def make_tool_dir(name: str):
        d = tmp_path / name / "package_tools"
        d.mkdir(parents=True)
        aapt_bytes = b"aapt2-v1"
        restool_bytes = b"restool-v1"
        (d / "aapt2.exe").write_bytes(aapt_bytes)
        (d / "restool.exe").write_bytes(restool_bytes)
        (d / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "platform": "windows-x64",
                    "files": {
                        "aapt2.exe": hashlib.sha256(aapt_bytes).hexdigest(),
                        "restool.exe": hashlib.sha256(restool_bytes).hexdigest(),
                    },
                }
            ),
            encoding="utf-8",
        )
        return MetadataTools(str(d / "aapt2.exe"), str(d / "restool.exe"))

    tools_run1 = make_tool_dir("mei_11111")
    tools_run2 = make_tool_dir("mei_22222")

    monkeypatch.setattr(loader_mod, "resolve_metadata_tools", lambda: tools_run1)
    done1 = threading.Event()
    loader1 = PackageLabelLoader(post=lambda fn: fn(), cache_path=cache_file, max_workers=1)
    try:
        loader1.submit([hap], lambda _g, _l, _f, done: done and done1.set(), priority_paths=[hap])
        assert done1.wait(timeout=5.0)
    finally:
        loader1.close()

    # Second run uses a totally different _MEIPASS path and must still hit disk cache without calling read_package_label.
    monkeypatch.setattr(loader_mod, "resolve_metadata_tools", lambda: tools_run2)
    monkeypatch.setattr(
        loader_mod,
        "read_package_label",
        lambda *_args, **_kw: (_ for _ in ()).throw(AssertionError("cache miss forced re-parse")),
    )
    done2 = threading.Event()
    batches2: list[tuple[dict, bool]] = []
    loader2 = PackageLabelLoader(post=lambda fn: fn(), cache_path=cache_file, max_workers=1)
    try:
        def on_update(_gen, labels, _fps, done):
            batches2.append((dict(labels), done))
            if done:
                done2.set()

        loader2.submit([hap], on_update, priority_paths=[hap])
        assert done2.wait(timeout=5.0)
        assert len(batches2) == 1
        assert batches2[0][1] is True
        assert batches2[0][0][hap].name == "跨重启命中应用"
    finally:
        loader2.close()
