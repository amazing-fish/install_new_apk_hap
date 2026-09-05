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


class FakeBooleanVar:
    def __init__(self, value: bool) -> None:
        self.value = value

    def get(self) -> bool:
        return self.value


class FakePreferenceConfig:
    def __init__(self) -> None:
        self.calls = []

    def set_apk_need_t(self, apk_name: str, needs_t: bool) -> None:
        self.calls.append((apk_name, needs_t))


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


def test_remember_apk_need_t_saves_checked_state() -> None:
    app = object.__new__(main.App)
    app.latest_apk = Path("demo.apk")
    app.apk_test_var = FakeBooleanVar(True)
    app.config_manager = FakePreferenceConfig()
    logged_messages = []
    app.log = logged_messages.append

    main.App.remember_apk_need_t(app)

    assert app.config_manager.calls == [("demo.apk", True)]
    assert logged_messages == ["已记住 APK 需要 -t: demo.apk"]


def test_remember_apk_need_t_removes_unchecked_state() -> None:
    app = object.__new__(main.App)
    app.latest_apk = Path("demo.apk")
    app.apk_test_var = FakeBooleanVar(False)
    app.config_manager = FakePreferenceConfig()
    logged_messages = []
    app.log = logged_messages.append

    main.App.remember_apk_need_t(app)

    assert app.config_manager.calls == [("demo.apk", False)]
    assert logged_messages == ["已取消 APK 的 -t 记忆: demo.apk"]
