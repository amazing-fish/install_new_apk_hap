"""Isolated real Tk application; no device discovery or user configuration."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import main


@pytest.fixture
def app(monkeypatch, tmp_path, request):
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
