"""Installation output channels must not override the command's exit status."""
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import main


CASES = [
    pytest.param(0, "", "Success\r\n", [], ["Success"], id="success-on-stderr"),
    pytest.param(0, "Success\n", "", ["Success"], [], id="success-on-stdout"),
    pytest.param(
        0, "Performing Streamed Install\n", "* daemon started successfully *\nSuccess\n",
        ["Performing Streamed Install"], ["* daemon started successfully *", "Success"],
        id="success-with-diagnostics",
    ),
    pytest.param(
        0, "", "Warning: diagnostic message\nSuccess\n", [],
        ["Warning: diagnostic message", "Success"], id="preserve-warning",
    ),
    pytest.param(
        1, "", "Failure [INSTALL_FAILED_TEST_ONLY]\n", [],
        ["Failure [INSTALL_FAILED_TEST_ONLY]"], id="failure-on-stderr",
    ),
    pytest.param(
        1, "Failure [INSTALL_FAILED_INVALID_APK]\n", "",
        ["Failure [INSTALL_FAILED_INVALID_APK]"], [], id="failure-on-stdout",
    ),
    pytest.param(1, "Success\n", "device offline\n", ["Success"], ["device offline"], id="mixed-failure"),
    pytest.param(1, "", "Success\n", [], ["Success"], id="exit-code-wins-over-text"),
    pytest.param(-15, "", "terminated\n", [], ["terminated"], id="terminated-command"),
    pytest.param(0, "", "", [], [], id="empty-success"),
    pytest.param(1, "", "", [], [], id="empty-failure"),
    pytest.param(0, None, None, [], [], id="uncaptured-output"),
]


@pytest.mark.parametrize("platform", ["Android", "Harmony"])
@pytest.mark.parametrize("returncode,stdout,stderr,stdout_lines,stderr_lines", CASES)
def test_install_result_logs_preserve_output_and_exit_status(
    platform, returncode, stdout, stderr, stdout_lines, stderr_lines,
):
    messages = []
    app = SimpleNamespace(_log_threadsafe=messages.append)
    command = ["installer", "package"]
    process = subprocess.CompletedProcess(command, returncode, stdout, stderr)
    result = main.InstallResult(command, process, 31.44)

    main.App._log_install_result(app, platform, "mate70紫色", result)

    prefix = f"{platform} mate70紫色"
    stderr_label = "输出 [stderr]" if returncode == 0 else "错误输出 [stderr]"
    assert messages == [
        f"{prefix} 安装结果: {returncode}，耗时 31.44 秒",
        *[f"{prefix} 输出: {line}" for line in stdout_lines],
        *[f"{prefix} {stderr_label}: {line}" for line in stderr_lines],
    ]
    assert (process.returncode, process.stdout, process.stderr) == (returncode, stdout, stderr)


@pytest.mark.parametrize("platform", ["android", "harmony"])
@pytest.mark.parametrize(
    "returncode,stdout,stderr,expected_status",
    [
        (0, "", "Success\n", "安装完成"),
        (1, "Failure [INSTALL_FAILED_INVALID_APK]\n", "", "安装失败"),
        (1, "", "Success\n", "安装失败"),
        (-15, "", "terminated\n", "安装失败"),
        (0, "", "[Fail][E001000] error\n", "安装失败"),
        (0, "Failure [INSTALL_FAILED_INVALID_APK]\n", "", "安装失败"),
    ],
)
def test_worker_status_uses_returncode_not_output_channel(
    monkeypatch, platform, returncode, stdout, stderr, expected_status,
):
    messages = []
    statuses = []
    command = ["installer", "package"]
    result = main.InstallResult(
        command, subprocess.CompletedProcess(command, returncode, stdout, stderr), 31.44,
    )
    app = SimpleNamespace(
        devices=[SimpleNamespace(device_id="device", platform=platform)],
        install_stop_event=threading.Event(),
        _device_label=lambda _device_id: "mate70紫色",
        _device_labels_for_log=lambda _selection: "mate70紫色",
        _log_threadsafe=messages.append,
        _finish_install=statuses.append,
        after=lambda _delay, callback, *args: callback(*args),
    )
    app._log_install_result = lambda *args: main.App._log_install_result(app, *args)
    for driver in main.DRIVERS.values():
        monkeypatch.setattr(driver, "install_command", lambda *_args, **_kwargs: command)
        monkeypatch.setattr(driver, "install", lambda *_args, **_kwargs: result)

    main.App._install_worker(app, ["device"], Path("app.apk"), Path("app.hap"), False)

    assert statuses == [expected_status]
    assert not any("安装线程异常" in message for message in messages)
    if expected_status == "安装完成":
        assert not any("错误输出" in message for message in messages)
        assert "输出 [stderr]: Success" in messages[-1]


FAILURE_MARKER_CASES = [
    pytest.param("", "[Fail][E001000] install parse profile prop check error\n", id="hdc-fail-code"),
    pytest.param("[Fail]Error while Deploying HAP\n", "", id="hdc-fail-stdout"),
    pytest.param("", "error: failed to install bundle.\n", id="hdc-error-line"),
    pytest.param("Performing Streamed Install\n", "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: x]\n", id="adb-failure"),
    pytest.param("", "adb: failed to install app.apk: Failure [INSTALL_FAILED_TEST_ONLY]\n", id="adb-failed-to-install"),
    pytest.param("  [Fail]indented\r\n", "", id="leading-whitespace-crlf"),
]


@pytest.mark.parametrize("stdout,stderr", FAILURE_MARKER_CASES)
def test_zero_exit_with_explicit_failure_marker_is_a_failure(stdout, stderr):
    command = ["installer", "package"]
    result = main.InstallResult(command, subprocess.CompletedProcess(command, 0, stdout, stderr), 1.0)

    assert result.failure_reason and result.failure_reason.startswith("输出包含失败标记")

    messages = []
    main.App._log_install_result(SimpleNamespace(_log_threadsafe=messages.append), "Harmony", "d", result)
    assert messages[-1].startswith("Harmony d 判定安装失败：输出包含失败标记")
    assert not any(" 输出 [stderr]" in message for message in messages)


@pytest.mark.parametrize("stdout,stderr", [
    pytest.param("", "Success\n", id="adb-success-stderr"),
    pytest.param("install bundle successfully.\nAppMod finish\n", "", id="hdc-success"),
    pytest.param("Performing Streamed Install\nSuccess\n", "", id="adb-streamed"),
    pytest.param("[Info]App install path:app.hap msg:install bundle successfully.\n", "", id="hdc-info-line"),
    pytest.param("installing, Failure [ will be printed on error\n", "", id="marker-not-at-line-start"),
])
def test_successful_outputs_are_not_treated_as_failures(stdout, stderr):
    command = ["installer", "package"]
    result = main.InstallResult(command, subprocess.CompletedProcess(command, 0, stdout, stderr), 1.0)
    assert result.failure_reason is None


def test_nonzero_exit_reason_does_not_depend_on_output():
    command = ["installer", "package"]
    result = main.InstallResult(command, subprocess.CompletedProcess(command, 1, "Success\n", ""), 1.0)
    assert result.failure_reason == "返回码 1"
