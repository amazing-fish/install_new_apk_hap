from __future__ import annotations

from pathlib import Path
import subprocess
import time

import platforms
from platforms.android import ANDROID
from platforms.base import DeviceInfo, InstallResult
from platforms.harmony import APP_LOG_TARGETS, HARMONY


def test_android_detect_parses_model_and_filters_emulator(monkeypatch):
    sample_output = "\n".join(
        [
            "List of devices attached",
            "emulator-5554          device product:sdk_gphone model:sdk_phone transport_id:1",
            "R5CW90ABCDE            device usb:1-2 product:e3qzcx model:SM_S9280 device:e3q transport_id:2",
            "ABC12345               unauthorized transport_id:3",
        ]
    )
    monkeypatch.setattr("platforms.android.resolve_adb_executable", lambda: "adb")
    monkeypatch.setattr("platforms.android.run_probe", lambda *a, **kw: sample_output)

    devices = ANDROID.detect()
    assert len(devices) == 2
    assert devices[0] == DeviceInfo(
        device_id="R5CW90ABCDE",
        platform="android",
        status="device",
        model="SM S9280",
        product="e3qzcx",
    )
    assert devices[1].device_id == "ABC12345"
    assert devices[1].status == "unauthorized"


def test_detect_devices_runs_concurrently_and_isolates_errors(monkeypatch):
    def slow_android(cancel=None):
        time.sleep(0.18)
        return [DeviceInfo("and-1", "android", "device", model="Pixel 9")]

    def slow_harmony(cancel=None):
        time.sleep(0.18)
        return [DeviceInfo("hm-1", "harmony", "device")]

    monkeypatch.setattr(ANDROID, "detect", slow_android)
    monkeypatch.setattr(HARMONY, "detect", slow_harmony)

    started = time.perf_counter()
    result = platforms.detect_devices()
    elapsed = time.perf_counter() - started

    assert [d.device_id for d in result.devices] == ["and-1", "hm-1"]
    assert result.errors == {}
    # Parallel execution must take notably less than 2 * 0.18s.
    assert elapsed < 0.32

    # Failure in Harmony preserves Android devices.
    def fail_harmony(cancel=None):
        raise HARMONY.tool_error("hdc missing")

    monkeypatch.setattr(HARMONY, "detect", fail_harmony)
    partial = platforms.detect_devices()
    assert [d.device_id for d in partial.devices] == ["and-1"]
    assert partial.harmony_error == "hdc missing"
    assert partial.android_error is None


def test_install_failure_markers_override_zero_exit_code():
    ok = InstallResult(["adb"], subprocess.CompletedProcess(["adb"], 0, "Success\n", ""), 1.2)
    assert ok.failure_reason is None

    hdc_fail = InstallResult(["hdc"], subprocess.CompletedProcess(["hdc"], 0, "[Fail][E001000] failed\n", ""), 1.0)
    assert hdc_fail.failure_reason is not None

    adb_fail = InstallResult(
        ["adb"], subprocess.CompletedProcess(["adb"], 0, "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]\n", ""), 1.0
    )
    assert adb_fail.failure_reason is not None

    nonzero = InstallResult(["adb"], subprocess.CompletedProcess(["adb"], 1, "Success\n", ""), 0.5)
    assert nonzero.failure_reason == "返回码 1"


def test_harmony_app_log_targets_match_fixed_paths():
    assert APP_LOG_TARGETS["qiankun"].remote_path == "/data/app/el2/100/base/com.yinwang.qiankunapp.hm/haps/phone/files/qklog/"
    assert APP_LOG_TARGETS["demo"].remote_path == "/data/app/el2/100/base/adsmobilesdk.all.huawei/haps/entry/files"
    cmd = ANDROID.install_command("dev1", Path("app.apk"), allow_test=True, executable="adb")
    assert cmd == ["adb", "-s", "dev1", "install", "-t", "app.apk"]
    cmd_no_t = ANDROID.install_command("dev1", Path("app.apk"), allow_test=False, executable="adb")
    assert cmd_no_t == ["adb", "-s", "dev1", "install", "app.apk"]
