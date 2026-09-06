from pathlib import Path
import threading
import time
import pytest

from services import package_label_loader as loader_module
from services.package_label_loader import PackageLabelLoader
from services.package_metadata import MetadataTools, PackageLabel


def test_worker_coalesces_requests_and_caches_unchanged_files(tmp_path, monkeypatch):
    paths = [tmp_path/f'{index}.apk' for index in range(3)]
    for path in paths:
        path.touch()
    entered, release = threading.Event(), threading.Event()
    calls = []
    monkeypatch.setattr(loader_module, 'resolve_metadata_tools', lambda: MetadataTools())
    def parse(path, tools):
        calls.append(path)
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return PackageLabel(path.stem, 'resolved')
    monkeypatch.setattr(loader_module, 'read_package_label', parse)
    loader = PackageLabelLoader()
    try:
        loader.submit(paths)
        assert entered.wait(2)
        loader.submit([paths[1]])
        generation = loader.submit([paths[2]])
        release.set()
        result = loader.results.get(timeout=3)
        assert result[0] == generation and list(result[1]) == [paths[2]]
        assert calls == [paths[0], paths[2]]
        loader.submit([paths[2]])
        loader.results.get(timeout=3)
        assert len(calls) == 2
        paths[2].write_bytes(b'rebuilt')
        loader.submit([paths[2]])
        loader.results.get(timeout=3)
        assert len(calls) == 3
    finally:
        release.set()
        loader.close()
        loader._thread.join(timeout=3)
    assert not loader._thread.is_alive()


def test_file_changed_during_read_is_not_cached_or_returned(tmp_path, monkeypatch):
    path = tmp_path/'changed.hap'
    path.touch()
    monkeypatch.setattr(loader_module, 'resolve_metadata_tools', lambda: MetadataTools())
    def parse(path, tools):
        path.write_bytes(path.read_bytes()+b'x')
        return PackageLabel('obsolete', 'resolved')
    monkeypatch.setattr(loader_module, 'read_package_label', parse)
    loader = PackageLabelLoader()
    try:
        loader.submit([path])
        assert loader.results.get(timeout=3)[1] == {}
    finally:
        loader.close()
        loader._thread.join(timeout=3)


def test_worker_recovers_after_unexpected_parser_failure(tmp_path, monkeypatch):
    path = tmp_path/'recover.apk'
    path.touch()
    monkeypatch.setattr(loader_module, 'resolve_metadata_tools', lambda: MetadataTools())
    def broken(*args):
        raise RuntimeError('parser failed')
    monkeypatch.setattr(loader_module, 'read_package_label', broken)
    loader = PackageLabelLoader()
    try:
        loader.submit([path])
        assert loader.results.get(timeout=3)[1][path].status == 'invalid'
        monkeypatch.setattr(loader_module, 'read_package_label', lambda *args: PackageLabel('Recovered', 'resolved'))
        loader.submit([path])
        assert loader.results.get(timeout=3)[1][path].name == 'Recovered'
    finally:
        loader.close()
        loader._thread.join(timeout=3)


@pytest.mark.parametrize('status', ['invalid', 'limited', 'tool_failed'])
def test_failed_reads_are_retried_with_unchanged_files_and_tools(tmp_path, monkeypatch, status):
    path = tmp_path / 'retry.hap'
    path.touch()
    monkeypatch.setattr(loader_module, 'resolve_metadata_tools', lambda: MetadataTools())
    results = iter([PackageLabel(status=status), PackageLabel('Recovered', 'resolved')])
    monkeypatch.setattr(loader_module, 'read_package_label', lambda *args: next(results))
    loader = PackageLabelLoader()
    try:
        loader.submit([path])
        assert loader.results.get(timeout=3)[1][path].status == status
        loader.submit([path])
        assert loader.results.get(timeout=3)[1][path].name == 'Recovered'
    finally:
        loader.close()
        loader._thread.join(timeout=3)
