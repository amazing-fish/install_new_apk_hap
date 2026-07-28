import sys
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

    main.App._set_refresh_state(app, True)
    assert app.refresh_button.settings["state"] == main.tk.DISABLED
    assert app.scan_button.settings["state"] == main.tk.DISABLED

    main.App._set_refresh_state(app, False)
    assert app.refresh_button.settings["state"] == main.tk.NORMAL
    assert app.scan_button.settings["state"] == main.tk.NORMAL


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
