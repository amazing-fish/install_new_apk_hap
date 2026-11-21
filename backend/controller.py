"""Task scheduling, target resolution, and concurrent/sequential multi-device installation."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
import subprocess
import threading
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from infra.tools import ToolError
from platforms import DeviceInfo, driver_for
from platforms.base import InstallResult, PlatformDriver


Post = Callable[[Callable[[], None]], None]
Spawn = Callable[[Callable[[], None]], None]
StructuredLog = Callable[[str, str, Optional[str]], None]  # (message, level, device_id)
DeviceProgressCallback = Callable[[str, str, str, Optional[float]], None]  # (device_id, state, detail, duration)


def spawn_daemon(function: Callable[[], None]) -> None:
    threading.Thread(target=function, daemon=True).start()


@dataclass
class Task:
    """One cancellable device operation, labelled `verb + name`."""
    action: str
    name: str
    verb: str = "获取"
    cancel: threading.Event = field(default_factory=threading.Event)
    pending: int = field(default=0, repr=False)

    @property
    def label(self) -> str:
        return self.verb + self.name

    @property
    def cancelled(self) -> bool:
        return self.cancel.is_set()


class TaskRunner:
    """At most one device task at a time; results are delivered through `post`."""

    def __init__(
        self,
        post: Post,
        spawn: Spawn = spawn_daemon,
        on_change: Callable[[], None] = lambda: None,
    ) -> None:
        self.post = post
        self.spawn = spawn
        self.on_change = on_change
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self.current: Optional[Task] = None

    @property
    def busy(self) -> bool:
        with self._lock:
            return self.current is not None

    def start(self, action: str, name: str, verb: str = "获取") -> Optional[Task]:
        with self._lock:
            if self.current is not None:
                return None
            self.current = Task(action, name, verb)
            task = self.current
        self.on_change()
        return task

    def run(
        self,
        task: Task,
        work: Callable[[], object],
        on_done: Callable[[object], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        def worker() -> None:
            try:
                result = work()
            except Exception as error:
                self.post(lambda failure=error: self._finish(task, on_error, failure))
                return
            self.post(lambda: self._finish(task, on_done, result))

        with self._lock:
            task.pending += 1
        self.spawn(worker)

    def _finish(self, task: Task, callback: Callable, value) -> None:
        try:
            callback(value)
        finally:
            changed = False
            with self._lock:
                task.pending -= 1
                if task.pending == 0 and self.current is task:
                    self.current = None
                    changed = True
                    self._cond.notify_all()
            if changed:
                self.on_change()

    def cancel(self, expected: Optional[Task] = None) -> bool:
        with self._lock:
            if (
                self.current is None
                or (expected is not None and self.current is not expected)
                or self.current.cancelled
            ):
                return False
            self.current.cancel.set()
        self.on_change()
        return True

    def wait_idle(self, timeout: float = 10.0) -> bool:
        with self._cond:
            return self._cond.wait_for(lambda: self.current is None, timeout=timeout)

    def background(
        self,
        work: Callable[[], object],
        on_done: Callable[[object], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        def worker() -> None:
            try:
                result = work()
            except Exception as error:
                self.post(lambda failure=error: on_error(failure))
                return
            self.post(lambda: on_done(result))

        self.spawn(worker)


def resolve_target(
    selection: Sequence[str],
    devices: Sequence[DeviceInfo],
    auto_select: bool = True,
) -> Optional[DeviceInfo]:
    """Single target device: the sole selected device, or the only online device when unambiguous."""
    if len(selection) == 1:
        return next((device for device in devices if device.device_id == selection[0]), None)
    if not selection and auto_select and len(devices) == 1:
        return devices[0]
    return None


@dataclass(frozen=True)
class InstallTarget:
    device_id: str
    label: str
    driver: Optional[PlatformDriver]
    package: Optional[Path]


def build_install_plan(
    device_ids: Iterable[str],
    devices: Sequence[DeviceInfo],
    packages: Dict[str, Optional[Path]],
    label_for: Callable[[str], str],
) -> List[InstallTarget]:
    """Freeze devices, drivers, and packages so mid-install refreshes cannot mutate targets."""
    platforms = {device.device_id: device.platform for device in devices}
    plan: List[InstallTarget] = []
    for device_id in device_ids:
        driver = driver_for(platforms.get(device_id, ""))
        package = packages.get(driver.package_kind) if driver else None
        plan.append(InstallTarget(device_id, label_for(device_id), driver, package))
    return plan


@dataclass
class InstallOutcome:
    cancelled: bool = False
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def status(self) -> str:
        if self.cancelled:
            return "已中止"
        if self.failed:
            return "安装失败"
        if self.skipped:
            return "安装未完成"
        return "安装完成"


def format_command_for_log(command: Iterable[str]) -> str:
    return subprocess.list2cmdline(list(command))


def _install_single_target(
    target: InstallTarget,
    allow_test: bool,
    cancel: threading.Event,
    log: StructuredLog,
    on_progress: Optional[DeviceProgressCallback],
) -> str:
    """Execute installation for one device. Returns 'cancelled'|'skipped'|'failed'|'succeeded'."""
    if cancel.is_set():
        if on_progress:
            on_progress(target.device_id, "cancelled", "已中止", None)
        return "cancelled"
    if target.driver is None or target.package is None:
        kind = target.driver.package_kind if target.driver else "可安装包"
        log(f"{target.label}: 未找到 {kind}，跳过", "warn", target.device_id)
        if on_progress:
            on_progress(target.device_id, "skipped", f"无 {kind}", None)
        return "skipped"

    driver = target.driver
    try:
        command = driver.install_command(target.device_id, target.package, allow_test=allow_test)
    except ToolError as error:
        log(f"{driver.label} {target.label} 安装失败（{error}）", "error", target.device_id)
        if on_progress:
            on_progress(target.device_id, "failed", str(error), None)
        return "failed"
    log(f"{driver.label} {target.label} 开始执行: {format_command_for_log(command)}", "cmd", target.device_id)
    if on_progress:
        on_progress(target.device_id, "installing", f"正在安装 {target.package.name}", None)

    def _stream_line(stream_name: str, line: str) -> None:
        prefix = "stderr" if stream_name == "stderr" else "输出"
        log(f"{driver.label} {target.label} [{prefix}]: {line}", "info", target.device_id)

    result = driver.install(command, cancel, on_output=_stream_line)

    if cancel.is_set():
        log(f"{driver.label} {target.label} 安装已中止（耗时 {result.duration_seconds:.2f} 秒）", "warn", target.device_id)
        if on_progress:
            on_progress(target.device_id, "cancelled", "已中止", result.duration_seconds)
        return "cancelled"

    failure_reason = result.failure_reason
    if failure_reason:
        log(
            f"{driver.label} {target.label} 安装失败（{failure_reason}，耗时 {result.duration_seconds:.2f} 秒）",
            "error",
            target.device_id,
        )
        if on_progress:
            on_progress(target.device_id, "failed", failure_reason, result.duration_seconds)
        return "failed"

    log(
        f"{driver.label} {target.label} 安装成功（返回码 0，耗时 {result.duration_seconds:.2f} 秒）",
        "success",
        target.device_id,
    )
    if on_progress:
        on_progress(target.device_id, "success", f"成功 · {result.duration_seconds:.1f}s", result.duration_seconds)
    return "succeeded"


def run_install_plan(
    plan: Sequence[InstallTarget],
    allow_test: bool,
    cancel: threading.Event,
    log: StructuredLog,
    *,
    parallel: bool = True,
    max_workers: int = 4,
    on_progress: Optional[DeviceProgressCallback] = None,
) -> InstallOutcome:
    """Install to all planned devices (concurrently by default) with live streaming logs."""
    outcome = InstallOutcome()
    mode_label = f"并行（上限 {min(max_workers, len(plan))}）" if parallel and len(plan) > 1 else "顺序"
    log(f"开始{mode_label}安装到所选设备（共 {len(plan)} 台）: {'，'.join(t.label for t in plan)}", "info", None)

    if on_progress:
        for target in plan:
            on_progress(target.device_id, "queued", "等待中", None)

    def _record(state: str) -> None:
        if state == "cancelled":
            outcome.cancelled = True
        elif state == "failed":
            outcome.failed += 1
        elif state == "skipped":
            outcome.skipped += 1
        elif state == "succeeded":
            outcome.succeeded += 1

    if not parallel or len(plan) <= 1:
        for target in plan:
            if cancel.is_set():
                outcome.cancelled = True
                if on_progress:
                    on_progress(target.device_id, "cancelled", "已中止", None)
                continue
            _record(_install_single_target(target, allow_test, cancel, log, on_progress))
        return outcome

    workers = max(1, min(max_workers, len(plan)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="device-install") as pool:
        futures = [
            pool.submit(_install_single_target, target, allow_test, cancel, log, on_progress)
            for target in plan
        ]
        for fut in as_completed(futures):
            _record(fut.result())

    return outcome
