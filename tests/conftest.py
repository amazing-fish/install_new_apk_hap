"""Isolated real Tk application; no device discovery or user configuration."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import main


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


class PendingSteps(list):
    def run_all(self):
        while self:
            self.pop(0)()


@pytest.fixture
def deferred_tasks(app):
    """Hold background steps so a test can observe the busy state; run_all() finishes them."""
    pending = PendingSteps()
    app.tasks.spawn = pending.append
    return pending


@pytest.fixture
def preflight(monkeypatch):
    """Set what the pre-install device check (detect_devices) will find."""
    from platforms import DeviceDetectionResult

    def set_devices(devices, **probe_errors):
        monkeypatch.setattr(main, 'detect_devices', lambda cancel=None: DeviceDetectionResult(list(devices), **probe_errors))
    return set_devices


@pytest.fixture
def install_plans(monkeypatch):
    """Record each frozen install plan as ([(device_id, package), ...], allow_test)."""
    from controller import InstallOutcome
    plans = []

    def run_install_plan(plan, allow_test, cancel, log):
        plans.append(([(target.device_id, target.package) for target in plan], allow_test))
        return InstallOutcome()
    monkeypatch.setattr(main, 'run_install_plan', run_install_plan)
    return plans


@pytest.fixture
def app(monkeypatch, tmp_path, request, hdc_executable, adb_executable):
    monkeypatch.setattr(main.App, '_get_config_path', lambda self: tmp_path / 'config.json')
    monkeypatch.setattr(main.App, 'refresh_devices', lambda self: None)
    monkeypatch.setattr(main.App, 'load_last_scan_dir', lambda self: None)
    configure = main.configure_window
    original_scale = []
    if hasattr(request, 'param'):
        def scaled_window(window):
            # Set the scale before configure_window realizes fonts and styles.
            original_scale.append(window.tk.call('tk', 'scaling'))
            window.tk.call('tk', 'scaling', request.param)
            configure(window)
        monkeypatch.setattr(main, 'configure_window', scaled_window)
    window = main.App()
    window.withdraw()
    # Device tasks run synchronously: an action call returns with its result applied.
    window.tasks.spawn = lambda work: work()
    window.tasks.post = lambda callback: callback()
    errors = []
    window.report_callback_exception = lambda *error: errors.append(error)
    try:
        yield window
    finally:
        window.update_idletasks()
        # Tk's display scale survives separate Tk interpreters in one process.
        if original_scale:
            window.tk.call('tk', 'scaling', original_scale[0])
        window.destroy()
        assert not errors, errors
