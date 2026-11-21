"""Shared fixtures: isolated tool paths and a fake external-process runner (no Tk, no devices)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


@pytest.fixture
def hdc_executable(monkeypatch, tmp_path):
    import os
    tool = tmp_path / 'SDK with spaces' / ('hdc.exe' if os.name == 'nt' else 'hdc')
    tool.parent.mkdir()
    tool.touch()
    tool.chmod(0o755)
    monkeypatch.setenv('HDC_EXECUTABLE', str(tool))
    return str(tool.resolve())


@pytest.fixture
def adb_executable(monkeypatch, tmp_path):
    import os
    tool = tmp_path / 'platform tools' / ('adb.exe' if os.name == 'nt' else 'adb')
    tool.parent.mkdir()
    tool.touch()
    tool.chmod(0o755)
    monkeypatch.setenv('ADB_EXECUTABLE', str(tool))
    return str(tool.resolve())


class FakeProcess:
    """Replace infra.process.run; handler(command, **kwargs) returns
    (returncode, stdout, stderr), a CompletedProcess, or raises OSError."""

    def __init__(self):
        self.calls = []
        self.handler = lambda command, **kwargs: (0, '', '')

    def __call__(self, command, **kwargs):
        from infra import process
        import subprocess
        command = [str(part) for part in command]
        self.calls.append((command, kwargs))
        try:
            outcome = self.handler(command, **kwargs)
        except OSError as error:
            raise process.ToolLaunchError(command, error) from error
        if isinstance(outcome, subprocess.CompletedProcess):
            outcome = (outcome.returncode, outcome.stdout or '', outcome.stderr or '')
        returncode, stdout, stderr, *flags = outcome
        return process.ProcessResult(
            command, returncode, stdout.encode('utf-8'), stderr.encode('utf-8'), 0.0,
            **(flags[0] if flags else {}), encoding='utf-8',
        )

    @property
    def commands(self):
        return [command for command, _kwargs in self.calls]


@pytest.fixture
def fake_process(monkeypatch):
    from infra import process
    fake = FakeProcess()
    monkeypatch.setattr(process, 'run', fake)
    return fake
