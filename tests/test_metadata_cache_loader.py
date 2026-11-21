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
