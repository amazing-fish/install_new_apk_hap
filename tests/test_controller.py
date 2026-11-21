from __future__ import annotations

from pathlib import Path
import subprocess
import threading
import time

from controller import InstallTarget, TaskRunner, build_install_plan, resolve_target, run_install_plan
from infra.tools import ToolError
from metadata import PackageLabel
from packages import PackageCandidate, PackageSlot, apk_allow_test
from platforms.base import DeviceInfo, InstallResult, PlatformDriver


class FakeDriver(PlatformDriver):
    key = "fake"
    label = "Fake"
    package_kind = "APK"

    def __init__(self, delay: float = 0.15, fail_ids: set[str] | None = None):
        self.delay = delay
        self.fail_ids = fail_ids or set()

    def install_command(self, device_id: str, package: Path, *, allow_test: bool = False, executable=None):
        return ["fake-tool", device_id, str(package), "-t" if allow_test else ""]

    def install(self, command, stop_event=None, on_output=None):
        device_id = command[1]
        if on_output:
            on_output("stdout", f"Streaming to {device_id}")
        time.sleep(self.delay)
        rc = 1 if device_id in self.fail_ids else 0
        out = "Failure [INSTALL_FAILED]" if rc else "Success"
        return InstallResult(command, subprocess.CompletedProcess(command, rc, out, ""), self.delay)


def test_parallel_install_is_faster_and_reports_per_device_progress():
    driver = FakeDriver(delay=0.16, fail_ids={"d2"})
    pkg = Path("app.apk")
    plan = [
        InstallTarget("d1", "Phone1", driver, pkg),
        InstallTarget("d2", "Phone2", driver, pkg),
        InstallTarget("d3", "Phone3", driver, None),  # skipped
    ]
    logs: list[tuple[str, str, str | None]] = []
    progress: dict[str, list[str]] = {}

    def on_progress(did, state, _detail, _dur):
        progress.setdefault(did, []).append(state)

    started = time.perf_counter()
    outcome = run_install_plan(
        plan,
        allow_test=True,
        cancel=threading.Event(),
        log=lambda msg, lvl, did: logs.append((msg, lvl, did)),
        parallel=True,
        max_workers=3,
        on_progress=on_progress,
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 0.30
    assert outcome.succeeded == 1
    assert outcome.failed == 1
    assert outcome.skipped == 1
    assert outcome.status == "安装失败"
    assert progress["d1"][-1] == "success"
    assert progress["d2"][-1] == "failed"
    assert progress["d3"][-1] == "skipped"
    assert any("Streaming to d1" in msg for msg, _, _ in logs)


def test_resolve_target_respects_selection_and_probe_failure():
    d1 = DeviceInfo("d1", "android", "device")
    d2 = DeviceInfo("d2", "harmony", "device")

    assert resolve_target([], [d1], auto_select=True) == d1
    assert resolve_target([], [d1], auto_select=False) is None
    assert resolve_target([], [d1, d2], auto_select=True) is None
    assert resolve_target(["d2"], [d1, d2], auto_select=False) == d2
    assert resolve_target(["d1", "d2"], [d1, d2], auto_select=True) is None


def test_apk_allow_test_policy(tmp_path: Path):
    import os

    p = tmp_path / "sample.apk"
    p.write_bytes(b"v1")
    slot = PackageSlot(candidates=[PackageCandidate.from_path(p)], index=0)
    # Unparsed metadata defaults to -t (installability first)
    assert apk_allow_test(slot) is True
    # Explicit testOnly=False omits -t when file fingerprint still matches
    slot.merge_labels({p: PackageLabel(name="App", status="resolved", test_only=False)})
    assert apk_allow_test(slot) is False
    # Modifying the file on disk invalidates the cached testOnly=False decision
    p.write_bytes(b"v2-modified")
    os.utime(p, (2_000_000_000, 2_000_000_000))
    assert apk_allow_test(slot) is True
    # Explicit testOnly=True keeps -t
    slot.merge_labels({p: PackageLabel(name="App", status="resolved", test_only=True)})
    assert apk_allow_test(slot) is True


def test_build_install_plan_freezes_packages():
    devices = [
        DeviceInfo("a1", "android", "device"),
        DeviceInfo("h1", "harmony", "device"),
    ]
    plan = build_install_plan(
        ["a1", "h1"],
        devices,
        {"APK": Path("a.apk"), "HAP": Path("h.hap")},
        lambda did: f"label-{did}",
    )
    assert len(plan) == 2
    assert plan[0].package == Path("a.apk")
    assert plan[1].package == Path("h.hap")


class MissingToolDriver(FakeDriver):
    def install_command(self, device_id: str, package: Path, *, allow_test: bool = False, executable=None):
        if device_id == "bad":
            raise ToolError("adb missing")
        return super().install_command(device_id, package, allow_test=allow_test, executable=executable)


def test_tool_error_in_install_command_does_not_abort_other_devices():
    driver = MissingToolDriver(delay=0.02)
    pkg = Path("app.apk")
    plan = [
        InstallTarget("bad", "BadPhone", driver, pkg),
        InstallTarget("good", "GoodPhone", driver, pkg),
    ]
    for parallel in (False, True):
        progress: dict[str, list[str]] = {}
        logs: list[str] = []
        outcome = run_install_plan(
            plan,
            allow_test=True,
            cancel=threading.Event(),
            log=lambda msg, _lvl, _did: logs.append(msg),
            parallel=parallel,
            max_workers=2,
            on_progress=lambda did, st, _det, _dur: progress.setdefault(did, []).append(st),
        )
        assert outcome.failed == 1
        assert outcome.succeeded == 1
        assert progress["bad"][-1] == "failed"
        assert progress["good"][-1] == "success"


def test_task_runner_cancel_expected_and_wait_idle():
    runner = TaskRunner(post=lambda fn: fn())
    task_a = runner.start("install", "A", verb="")
    assert task_a is not None
    gate = threading.Event()
    runner.run(task_a, lambda: gate.wait(timeout=2.0), lambda _r: None, lambda _e: None)

    assert runner.cancel(expected=task_a) is True
    gate.set()
    assert runner.wait_idle(timeout=2.0) is True

    task_b = runner.start("udid", "B")
    assert task_b is not None
    gate2 = threading.Event()
    runner.run(task_b, lambda: gate2.wait(timeout=2.0), lambda _r: None, lambda _e: None)
    # Stale cancel targeting task_a must NOT cancel task_b
    assert runner.cancel(expected=task_a) is False
    assert task_b.cancelled is False
    gate2.set()
    assert runner.wait_idle(timeout=2.0) is True
