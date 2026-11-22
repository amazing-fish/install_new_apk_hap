"""Priority-ordered concurrent metadata loader with incremental callbacks and disk cache."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
import hashlib
import json
from pathlib import Path
import threading
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from infra.tools import MetadataTools, resolve_metadata_tools
from metadata import PackageLabel, read_package_label
from metadata.cache import PersistentMetadataCache, make_cache_key


_TOOL_HASH_CACHE: Dict[tuple, str] = {}
_TOOL_HASH_LOCK = threading.Lock()


def file_fingerprint(path: Path) -> tuple:
    stat = path.stat()
    return (str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)


def tool_fingerprint(tool_path: Optional[str]) -> Optional[tuple]:
    """Return a stable content/manifest fingerprint immune to onefile temp path changes."""
    if not tool_path:
        return None
    path = Path(tool_path)
    manifest_path = path.with_name("manifest.json")
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            files = manifest.get("files")
            if isinstance(files, dict):
                expected = files.get(path.name)
                if isinstance(expected, str) and len(expected) == 64:
                    return ("manifest-sha256", path.name, expected)
        except (OSError, ValueError):
            pass

    try:
        st = path.stat()
        stat_key = (str(path.resolve()), st.st_size, st.st_mtime_ns)
    except OSError:
        return ("missing", str(path))

    with _TOOL_HASH_LOCK:
        cached = _TOOL_HASH_CACHE.get(stat_key)
    if cached is not None:
        return ("file-sha256", path.name, cached)

    try:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(65536):
                hasher.update(chunk)
        digest = hasher.hexdigest()
    except OSError:
        return ("stat", path.name, st.st_size, st.st_mtime_ns)

    with _TOOL_HASH_LOCK:
        _TOOL_HASH_CACHE[stat_key] = digest
    return ("file-sha256", path.name, digest)


class PackageLabelLoader:
    """Coalescing, priority-first concurrent metadata loader.

    - Serves persistent/in-memory cache hits immediately in a first fast batch.
    - Parses priority paths (e.g., currently selected newest APK & HAP) first so
      active cards update without waiting for the rest of the directory.
    - Parses remaining candidates concurrently with a bounded worker pool and
      streams incremental batches through `post(on_done)`.
    - Drops superseded generations automatically.
    """

    def __init__(
        self,
        post: Callable[[Callable[[], None]], None],
        *,
        cache_path: Optional[Path] = None,
        max_workers: int = 4,
    ) -> None:
        self.post = post
        self._cache_path = cache_path
        self._cache_lock = threading.Lock()
        self._cache: Optional[PersistentMetadataCache] = None
        self._max_workers = max(1, max_workers)
        self._condition = threading.Condition()
        self._generation = 0
        self._pending: Optional[Tuple[int, Tuple[Path, ...], Tuple[Path, ...], Callable[[int, dict, dict, bool], None]]] = None
        self._closed = False
        self._thread: Optional[threading.Thread] = None

    def _get_cache(self) -> PersistentMetadataCache:
        with self._cache_lock:
            if self._cache is None:
                self._cache = PersistentMetadataCache(cache_path=self._cache_path)
            return self._cache

    def submit(
        self,
        paths: List[Path],
        on_update: Callable[[int, Dict[Path, PackageLabel], Dict[Path, tuple], bool], None],
        *,
        priority_paths: Iterable[Path] = (),
    ) -> int:
        """Queue a scan generation. `on_update(generation, labels, fingerprints, done)` may fire multiple times."""
        prio_set = list(dict.fromkeys(priority_paths))
        ordered_paths = list(dict.fromkeys(paths))
        with self._condition:
            self._generation += 1
            self._pending = (self._generation, tuple(ordered_paths), tuple(prio_set), on_update)
            if self._thread is None:
                self._thread = threading.Thread(target=self._work, daemon=True, name="metadata-loader")
                self._thread.start()
            self._condition.notify()
            return self._generation

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._pending = None
            self._condition.notify()
        with self._cache_lock:
            cache = self._cache
        if cache is not None:
            cache.flush()

    def _is_stale(self, generation: int) -> bool:
        with self._condition:
            return self._closed or generation != self._generation

    def _parse_one(
        self,
        path: Path,
        tools: MetadataTools,
        tool_key: tuple,
        generation: int,
    ) -> Optional[Tuple[Path, PackageLabel, tuple]]:
        if self._is_stale(generation):
            return None
        try:
            fp = file_fingerprint(path)
        except OSError:
            return None
        cache = self._get_cache()
        cache_key = make_cache_key(fp, tool_key)
        cached = cache.get(cache_key)
        if cached is not None:
            return path, cached, fp
        label = read_package_label(path, tools)
        try:
            if fp != file_fingerprint(path):
                return None
        except OSError:
            return None
        cache.put(cache_key, label)
        return path, label, fp

    def _work(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending is not None or self._closed)
                if self._closed:
                    return
                assert self._pending is not None
                generation, paths, priority_paths, on_update = self._pending
                self._pending = None

            if not paths:
                if not self._is_stale(generation):
                    self.post(partial(on_update, generation, {}, {}, True))
                continue

            try:
                tools = resolve_metadata_tools()
                tool_key = tuple(tool_fingerprint(p) for p in (tools.aapt2, tools.restool))
            except Exception:
                labels = {path: PackageLabel(status="invalid") for path in paths}
                fps = {}
                for path in paths:
                    try:
                        fps[path] = file_fingerprint(path)
                    except OSError:
                        pass
                if not self._is_stale(generation):
                    self.post(partial(on_update, generation, labels, fps, True))
                continue

            # Phase 1: Instant cache hits for any file already known.
            cache = self._get_cache()
            cached_labels: Dict[Path, PackageLabel] = {}
            cached_fps: Dict[Path, tuple] = {}
            uncached: List[Path] = []
            for path in paths:
                if self._is_stale(generation):
                    break
                try:
                    fp = file_fingerprint(path)
                except OSError:
                    continue
                hit = cache.get(make_cache_key(fp, tool_key))
                if hit is not None:
                    cached_labels[path] = hit
                    cached_fps[path] = fp
                else:
                    uncached.append(path)

            if self._is_stale(generation):
                continue

            if cached_labels:
                self.post(partial(on_update, generation, cached_labels, cached_fps, not uncached))
                if not uncached:
                    continue
            elif not uncached:
                self.post(partial(on_update, generation, {}, {}, True))
                continue

            # Phase 2: Split uncached into priority (active/newest) vs rest.
            prio_set = set(priority_paths)
            prio_queue = [p for p in uncached if p in prio_set]
            rest_queue = [p for p in uncached if p not in prio_set]

            with ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="meta-parse") as pool:
                # 2a: Priority batch first, emit immediately when done.
                if prio_queue and not self._is_stale(generation):
                    prio_labels: Dict[Path, PackageLabel] = {}
                    prio_fps: Dict[Path, tuple] = {}
                    futures = [pool.submit(self._parse_one, p, tools, tool_key, generation) for p in prio_queue]
                    for fut in as_completed(futures):
                        if self._is_stale(generation):
                            break
                        res = fut.result()
                        if res is not None:
                            p, lbl, fp = res
                            prio_labels[p] = lbl
                            prio_fps[p] = fp
                    if not self._is_stale(generation):
                        self.post(partial(on_update, generation, prio_labels, prio_fps, not rest_queue))

                # 2b: Remaining files in incremental chunks so UI stays lively.
                if rest_queue and not self._is_stale(generation):
                    batch_labels: Dict[Path, PackageLabel] = {}
                    batch_fps: Dict[Path, tuple] = {}
                    futures = [pool.submit(self._parse_one, p, tools, tool_key, generation) for p in rest_queue]
                    for fut in as_completed(futures):
                        if self._is_stale(generation):
                            break
                        res = fut.result()
                        if res is not None:
                            p, lbl, fp = res
                            batch_labels[p] = lbl
                            batch_fps[p] = fp
                            if len(batch_labels) >= 4:
                                if not self._is_stale(generation):
                                    self.post(partial(on_update, generation, dict(batch_labels), dict(batch_fps), False))
                                batch_labels.clear()
                                batch_fps.clear()
                    if not self._is_stale(generation):
                        self.post(partial(on_update, generation, batch_labels, batch_fps, True))

            cache.flush()
