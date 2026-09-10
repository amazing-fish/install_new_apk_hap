import sys
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main


class FakeButton:
    def __init__(self) -> None:
        self.settings = {}

    def config(self, **kwargs) -> None:
        self.settings.update(kwargs)


def test_refresh_buttons_share_device_and_package_refresh() -> None:
    app = object.__new__(main.App)
    calls = []
    app.refresh_devices = lambda: calls.append("devices")
    app.scan_latest_packages = lambda: calls.append("packages")

    main.App.refresh_devices_and_packages(app)

    assert calls == ["devices", "packages"]


def test_refresh_state_controls_both_refresh_entry_points() -> None:
    app = object.__new__(main.App)
    app.refresh_button = FakeButton()
    app.scan_button = FakeButton()
    app._update_device_actions = lambda: None

    main.App._set_refresh_state(app, True)
    assert app.refresh_button.settings["state"] == main.tk.DISABLED
    assert app.scan_button.settings["state"] == main.tk.DISABLED

    main.App._set_refresh_state(app, False)
    assert app.refresh_button.settings["state"] == main.tk.NORMAL
    assert app.scan_button.settings["state"] == main.tk.NORMAL


def test_threadsafe_log_captures_timestamp_before_tk_callback(monkeypatch) -> None:
    app = object.__new__(main.App)
    scheduled_callbacks = []
    appended_entries = []
    worker_thread = object()
    main_thread = object()

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 28, 20, 35, 9)

    app.after = lambda delay, callback, *args: scheduled_callbacks.append(
        (delay, callback, args)
    )
    app._append_log_entry = lambda timestamp, message: appended_entries.append(
        (timestamp, message)
    )
    monkeypatch.setattr(main, "datetime", FixedDateTime)
    monkeypatch.setattr(main.threading, "current_thread", lambda: worker_thread)
    monkeypatch.setattr(main.threading, "main_thread", lambda: main_thread)

    main.App._log_threadsafe(app, "Harmony 开始执行命令")

    assert appended_entries == []
    assert len(scheduled_callbacks) == 1
    delay, callback, args = scheduled_callbacks[0]
    assert delay == 0
    assert args == ("20:35:09", "Harmony 开始执行命令")

    callback(*args)
    assert appended_entries == [
        ("20:35:09", "Harmony 开始执行命令"),
    ]
