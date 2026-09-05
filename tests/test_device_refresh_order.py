import sys
import subprocess
import threading
import pytest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main
from services.device_detector import DeviceInfo
from services.installer import InstallResult


class FakeTree:
    columns = ("device_id", "name", "status", "platform")

    def __init__(self, selection=()) -> None:
        self.items = {}
        self.order = []
        self._selection = tuple(selection)
        self.config = {}

    def selection(self):
        return self._selection

    def selection_set(self, *selection) -> None:
        if len(selection) == 1 and isinstance(selection[0], str):
            self._selection = (selection[0],)
        elif len(selection) == 1:
            self._selection = tuple(selection[0])
        else:
            self._selection = tuple(selection)

    def get_children(self):
        return tuple(self.order)

    def delete(self, *items) -> None:
        for item in items:
            self.items.pop(item, None)
            if item in self.order:
                self.order.remove(item)
        self._selection = tuple(item for item in self._selection if item in self.items)

    def insert(self, _parent, _index, iid, values, tags=()) -> None:
        self.items[iid] = {"values": list(values), "tags": tuple(tags)}
        self.order.append(iid)

    def set(self, iid, column, value=None):
        column_index = self.columns.index(column)
        if value is None:
            return self.items[iid]["values"][column_index]
        self.items[iid]["values"][column_index] = value
        return None

    def configure(self, **kwargs) -> None:
        self.config.update(kwargs)


class FakeVar:
    def __init__(self) -> None:
        self.value = None

    def set(self, value) -> None:
        self.value = value


class FakeButton:
    def __init__(self) -> None:
        self.settings = {}

    def config(self, **kwargs) -> None:
        self.settings.update(kwargs)


class FakeConfig:
    def __init__(self, names=None) -> None:
        self.data = {"device_names": names or {}}


@pytest.fixture(autouse=True)
def isolate_tk_column_measurement(monkeypatch):
    # These tests cover refresh ordering with a non-Tk tree; real columns are
    # exercised by test_ui_usability on the actual widget.
    monkeypatch.setattr(main, 'fit_device_columns', lambda tree: None)


def make_app(previous_device_ids, selection=(), names=None):
    app = object.__new__(main.App)
    app.device_tree = FakeTree(selection=selection)
    app.name_var = FakeVar()
    app.device_summary_var = FakeVar()
    app.selected_device_summary_var = FakeVar()
    app.config_manager = FakeConfig(names=names)
    app.devices = []
    app.device_ids_before_last_refresh = previous_device_ids
    app._last_device_refresh_snapshot = None
    app.refresh_button = FakeButton()
    app.scan_button = FakeButton()
    app.logged_messages = []
    app.log = app.logged_messages.append
    app._update_device_actions = lambda: None
    return app


def test_reorder_devices_for_refresh_moves_new_devices_to_top() -> None:
    previous_ids = {"old-android", "old-harmony"}
    devices = [
        DeviceInfo(device_id="old-android", platform="android", status="device"),
        DeviceInfo(device_id="new-harmony", platform="harmony", status="device"),
        DeviceInfo(device_id="old-harmony", platform="harmony", status="device"),
        DeviceInfo(device_id="new-android", platform="android", status="device"),
    ]

    assert hasattr(main, "reorder_devices_for_refresh")

    ordered_devices, new_ids = main.reorder_devices_for_refresh(devices, previous_ids)

    assert [device.device_id for device in ordered_devices] == [
        "new-harmony",
        "new-android",
        "old-android",
        "old-harmony",
    ]
    assert new_ids == {"new-harmony", "new-android"}


def test_build_crash_log_target_dispatches_by_device_platform() -> None:
    output_dir = Path("D:/")

    android_target = main.build_crash_log_target(
        DeviceInfo(device_id="android-device", platform="android", status="device"),
        output_dir,
    )
    harmony_target = main.build_crash_log_target(
        DeviceInfo(device_id="harmony-device", platform="harmony", status="device"),
        output_dir,
    )

    assert android_target.platform == "android"
    assert android_target.output_path == output_dir / "crash.log"
    assert harmony_target.platform == "harmony"
    assert harmony_target.output_path == output_dir


def test_get_device_display_name_prefers_saved_name() -> None:
    name_mapping = {
        "android-device": "Pixel 8",
        "blank-device": "  ",
    }

    assert main.get_device_display_name("android-device", name_mapping) == "Pixel 8"
    assert main.get_device_display_name("blank-device", name_mapping) == "blank-device"
    assert main.get_device_display_name("unknown-device", name_mapping) == "unknown-device"


def test_format_device_ids_for_log_uses_saved_names() -> None:
    name_mapping = {
        "android-device": "Pixel 8",
        "harmony-device": "Mate 70",
    }

    assert main.format_device_ids_for_log(
        ["android-device", "unknown-device", "harmony-device"],
        name_mapping,
    ) == "Pixel 8，unknown-device，Mate 70"


def test_apply_device_refresh_preserves_still_connected_selection() -> None:
    app = make_app(
        previous_device_ids={"old-android", "old-harmony"},
        selection=("old-harmony",),
        names={"old-harmony": "Mate 70"},
    )
    devices = [
        DeviceInfo(device_id="old-android", platform="android", status="device"),
        DeviceInfo(device_id="new-harmony", platform="harmony", status="device"),
        DeviceInfo(device_id="old-harmony", platform="harmony", status="device"),
    ]

    main.App._apply_device_refresh(app, devices)

    assert app.device_tree.order == ["new-harmony", "old-android", "old-harmony"]
    assert app.device_tree.selection() == ("old-harmony",)
    assert app.name_var.value == "Mate 70"


def test_apply_device_refresh_restores_explicit_multi_device_install_snapshot() -> None:
    app = make_app(
        previous_device_ids={"android-a", "android-b", "harmony-c"},
        selection=(),
    )
    devices = [
        DeviceInfo(device_id="android-a", platform="android", status="device"),
        DeviceInfo(device_id="android-b", platform="android", status="device"),
        DeviceInfo(device_id="harmony-c", platform="harmony", status="device"),
    ]

    main.App._apply_device_refresh(
        app,
        devices,
        selection_to_restore={"android-a", "harmony-c"},
    )

    assert app.device_tree.selection() == ("android-a", "harmony-c")


def test_finalize_install_restores_snapshot_and_keeps_target_order(monkeypatch) -> None:
    app = make_app(
        previous_device_ids={"android-a", "android-b", "harmony-c"},
        selection=(),
    )
    devices = [
        DeviceInfo(device_id="android-a", platform="android", status="device"),
        DeviceInfo(device_id="android-b", platform="android", status="device"),
        DeviceInfo(device_id="harmony-c", platform="harmony", status="device"),
    ]
    started_threads = []

    class FakeThread:
        def __init__(self, *, target, args, daemon) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self) -> None:
            started_threads.append(self)

    monkeypatch.setattr(main.threading, "Thread", FakeThread)

    main.App._finalize_install(
        app,
        devices,
        previous_selection={"android-a", "harmony-c"},
        selected_apk=Path("demo.apk"),
        selected_hap=Path("demo.hap"),
        allow_test=True,
        validation_duration_seconds=1.25,
    )

    assert app.device_tree.selection() == ("android-a", "harmony-c")
    assert len(started_threads) == 1
    assert started_threads[0].args == (
        ["android-a", "harmony-c"],
        Path("demo.apk"),
        Path("demo.hap"),
        True,
    )
    assert app.logged_messages[0].startswith(
        "安装前设备校验完成（耗时 1.25 秒）："
    )


def test_install_worker_logs_command_before_harmony_result(monkeypatch, hdc_executable) -> None:
    app = object.__new__(main.App)
    app.devices = [
        DeviceInfo(device_id="harmony-device", platform="harmony", status="device"),
    ]
    app.install_stop_event = threading.Event()
    app.config_manager = FakeConfig(names={"harmony-device": "Mate 70"})
    app.logged_messages = []
    app._log_threadsafe = app.logged_messages.append
    app.after = lambda *_args: None
    hap_path = Path("Harmony release.hap")

    def fake_install_harmony(device_id, selected_hap, stop_event, **kwargs):
        assert kwargs['hdc_executable'] == hdc_executable
        assert device_id == "harmony-device"
        assert selected_hap == hap_path
        assert stop_event is app.install_stop_event
        assert "开始执行命令" in app.logged_messages[-1]
        return InstallResult(
            command=["hdc", "-t", device_id, "install", str(selected_hap)],
            process=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="[Info]install bundle successfully.\nAppMod finish",
                stderr="",
            ),
            duration_seconds=15.236,
        )

    monkeypatch.setattr(main, "install_harmony", fake_install_harmony)

    main.App._install_worker(
        app,
        ["harmony-device"],
        selected_apk=None,
        selected_hap=hap_path,
        allow_test=False,
    )

    assert app.logged_messages == [
        "开始安装到所选设备: Mate 70",
        (
            "Harmony Mate 70 开始执行命令: "
            f'"{hdc_executable}" -t harmony-device install "Harmony release.hap"'
        ),
        "Harmony Mate 70 安装结果: 0，耗时 15.24 秒",
        "Harmony Mate 70 输出: [Info]install bundle successfully.",
        "Harmony Mate 70 输出: AppMod finish",
    ]


def test_stale_refresh_result_does_not_replace_newer_device_list() -> None:
    app = object.__new__(main.App)
    app._latest_refresh_request_id = 2
    applied_results = []

    def record_apply(devices):
        applied_results.append(devices)

    app._apply_device_refresh = record_apply
    stale_devices = [DeviceInfo(device_id="stale", platform="android", status="device")]
    current_devices = [DeviceInfo(device_id="current", platform="android", status="device")]

    main.App._apply_device_refresh_result(app, 1, stale_devices)
    main.App._apply_device_refresh_result(app, 2, current_devices)

    assert applied_results == [current_devices]
