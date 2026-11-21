"""Installation output channels must not override the command's exit status."""
import subprocess
import threading
from pathlib import Path

import pytest

from platforms import DeviceInfo
from platforms.base import InstallResult


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
    result = InstallResult(command, subprocess.CompletedProcess(command, 0, stdout, stderr), 1.0)

    assert result.failure_reason and result.failure_reason.startswith("输出包含失败标记")



@pytest.mark.parametrize("stdout,stderr", [
    pytest.param("", "Success\n", id="adb-success-stderr"),
    pytest.param("install bundle successfully.\nAppMod finish\n", "", id="hdc-success"),
    pytest.param("Performing Streamed Install\nSuccess\n", "", id="adb-streamed"),
    pytest.param("[Info]App install path:app.hap msg:install bundle successfully.\n", "", id="hdc-info-line"),
    pytest.param("installing, Failure [ will be printed on error\n", "", id="marker-not-at-line-start"),
])
def test_successful_outputs_are_not_treated_as_failures(stdout, stderr):
    command = ["installer", "package"]
    result = InstallResult(command, subprocess.CompletedProcess(command, 0, stdout, stderr), 1.0)
    assert result.failure_reason is None


def test_nonzero_exit_reason_does_not_depend_on_output():
    command = ["installer", "package"]
    result = InstallResult(command, subprocess.CompletedProcess(command, 1, "Success\n", ""), 1.0)
    assert result.failure_reason == "返回码 1"
