"""One coalescing metadata worker. No Tk objects cross the thread boundary."""
from collections import OrderedDict
from functools import partial
from pathlib import Path
import threading
from typing import Callable

from infra.tools import resolve_metadata_tools
from metadata import PackageLabel, read_package_label


def file_fingerprint(path: Path) -> tuple:
    stat = path.stat()
    return (path.resolve(), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)


class PackageLabelLoader:
    """Only the latest request is read; a superseded one is dropped unread.

    Results reach `on_done(generation, labels, fingerprints)` through `post`,
    which is called on the worker thread and must be thread-safe.
    """

    def __init__(self, post: Callable[[Callable[[], None]], None]):
        self.post = post
        self._condition = threading.Condition()
        self._generation = 0
        self._pending = None
        self._closed = False
        self._thread = None

    def submit(self, paths: list[Path], on_done: Callable[[int, dict, dict], None]) -> int:
        with self._condition:
            self._generation += 1
            self._pending = (self._generation, tuple(paths), on_done)
            if self._thread is None:
                self._thread = threading.Thread(target=self._work, args=(), daemon=True)
                self._thread.start()
            self._condition.notify()
            return self._generation

    def close(self):
        with self._condition:
            self._closed = True
            self._pending = None
            self._condition.notify()

    def _work(self):
        cache = OrderedDict()
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending is not None or self._closed)
                if self._closed:
                    return
                generation, paths, on_done = self._pending
                self._pending = None
            labels, fingerprints = {}, {}
            try:
                tools = resolve_metadata_tools()
                tool_key = tuple(file_fingerprint(Path(p)) if p else None for p in (tools.aapt2, tools.restool))
                for path in paths:
                    with self._condition:
                        if self._closed or generation != self._generation:
                            break
                    try:
                        fingerprint = file_fingerprint(path)
                        key = (fingerprint, tool_key)
                        label = cache.get(key)
                        if label is None:
                            label = read_package_label(path, tools)
                        if fingerprint != file_fingerprint(path):
                            continue
                        # Retry transient read/tool failures on the next refresh.
                        if label.status not in ('invalid', 'limited', 'tool_failed'):
                            cache[key] = label
                            cache.move_to_end(key)
                            while len(cache) > 256:
                                cache.popitem(last=False)
                        labels[path], fingerprints[path] = label, fingerprint
                    except OSError:
                        continue
            except Exception:
                # A resolver/parser bug must not kill the worker permanently.
                labels = {path: PackageLabel(status='invalid') for path in paths}
                fingerprints = {}
                for path in paths:
                    try:
                        fingerprints[path] = file_fingerprint(path)
                    except OSError:
                        pass
            with self._condition:
                if self._closed:
                    return
                if generation != self._generation:
                    continue
            # Outside the lock: `post` may run on_done synchronously. A request
            # submitted meanwhile is filtered by the receiver's own generation.
            self.post(partial(on_done, generation, labels, fingerprints))
