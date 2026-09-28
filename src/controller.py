"""Tk-free task scheduling and device-action rules, testable without a window."""
from dataclasses import dataclass, field
import subprocess
import threading
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from platforms import DeviceInfo, driver_for
from platforms.base import InstallResult, PlatformDriver


Post = Callable[[Callable[[], None]], None]
Spawn = Callable[[Callable[[], None]], None]


def spawn_daemon(function: Callable[[], None]) -> None:
    threading.Thread(target=function, daemon=True).start()


@dataclass
class Task:
    """One cancellable device operation, labelled `verb + name` (获取 + 崩溃日志)."""
    action: str
    name: str
    verb: str = "获取"
    cancel: threading.Event = field(default_factory=threading.Event)
    pending: int = field(default=0, repr=False)  # steps started but not yet delivered

    @property
    def label(self) -> str:
        return self.verb + self.name

    @property
    def cancelled(self) -> bool:
        return self.cancel.is_set()


class TaskRunner:
    """At most one device task at a time; results are delivered through `post`.

    `post` runs a callable on the UI thread and `spawn` runs one in the
    background, so tests can inject synchronous versions of both.
    """

    def __init__(self, post: Post, spawn: Spawn = spawn_daemon,
                 on_change: Callable[[], None] = lambda: None) -> None:
        self.post = post
        self.spawn = spawn
        self.on_change = on_change
        self.current: Optional[Task] = None

    @property
    def busy(self) -> bool:
        return self.current is not None

    def start(self, action: str, name: str, verb: str = "获取") -> Optional[Task]:
        """Claim the slot; None when another task is still running."""
        if self.current is not None:
            return None
        self.current = Task(action, name, verb)
        self.on_change()
        return self.current

    def run(self, task: Task, work: Callable[[], object],
            on_done: Callable[[object], None], on_error: Callable[[Exception], None]) -> None:
        """Run one step of `task`; the slot is released after the callback
        unless that callback started the task's next step with `run`."""
        def worker() -> None:
            try:
                result = work()
            except Exception as error:  # delivered to the UI thread, never lost
                # `error` is unbound when the except block ends: bind it now.
                self.post(lambda failure=error: self._finish(task, on_error, failure))
                return
            self.post(lambda: self._finish(task, on_done, result))

        task.pending += 1
        self.spawn(worker)

    def _finish(self, task: Task, callback: Callable, value) -> None:
        task.pending -= 1
        try:
            callback(value)
        finally:
            if task.pending == 0 and self.current is task:
                self.current = None
                self.on_change()

    def cancel(self) -> bool:
        if self.current is None or self.current.cancelled:
            return False
        self.current.cancel.set()
        self.on_change()
        return True

    def background(self, work: Callable[[], object], on_done: Callable[[object], None],
                   on_error: Callable[[Exception], None]) -> None:
        """Slot-free background work (device refresh) with the same delivery."""
        def worker() -> None:
            try:
                result = work()
            except Exception as error:
                self.post(lambda failure=error: on_error(failure))
                return
            self.post(lambda: on_done(result))

        self.spawn(worker)


def resolve_target(selection: Sequence[str], devices: Sequence[DeviceInfo],
                   auto_select: bool = True) -> Optional[DeviceInfo]:
    """The one device a single-device action applies to.

    The selected device when exactly one is selected; with nothing selected,
    the only connected device. `auto_select` is False after a failed probe,
    when the "only" device may not be the only one.
    """
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


def build_install_plan(device_ids: Iterable[str], devices: Sequence[DeviceInfo],
                       packages: Dict[str, Optional[Path]],
                       label_for: Callable[[str], str]) -> List[InstallTarget]:
    """Freeze everything the install worker needs, on the UI thread.

    A refresh during the install then cannot change what gets installed where.
    """
    platforms = {device.device_id: device.platform for device in devices}
    plan = []
    for device_id in device_ids:
        driver = driver_for(platforms.get(device_id, ""))
        package = packages.get(driver.package_kind) if driver else None
        plan.append(InstallTarget(device_id, label_for(device_id), driver, package))
    return plan


@dataclass
class InstallOutcome:
    cancelled: bool = False
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


def run_install_plan(plan: Sequence[InstallTarget], allow_test: bool, cancel: threading.Event,
                     log: Callable[[str], None]) -> InstallOutcome:
    """Install sequentially; `log` must be safe to call from this thread."""
    outcome = InstallOutcome()
    log(f"开始安装到所选设备: {'，'.join(target.label for target in plan)}")
    for target in plan:
        if cancel.is_set():
            outcome.cancelled = True
            log("安装已中止")
            break
        if target.driver is None or target.package is None:
            outcome.skipped += 1
            kind = target.driver.package_kind if target.driver else "可安装包"
            log(f"{target.label}: 未找到 {kind}，跳过")
            continue
        # Resolve the tool once: the logged command is the executed command.
        command = target.driver.install_command(target.device_id, target.package, allow_test=allow_test)
        log(f"{target.driver.label} {target.label} 开始执行命令: {format_command_for_log(command)}")
        result = target.driver.install(command, cancel)
        log_install_result(target.driver.label, target.label, result, log)
        if cancel.is_set():
            outcome.cancelled = True
            log(f"{target.label}: 安装已中止")
            break
        if result.failure_reason:
            outcome.failed += 1
    return outcome


def log_install_result(platform: str, device_label: str, result: InstallResult,
                       log: Callable[[str], None]) -> None:
    log(f"{platform} {device_label} 安装结果: {result.process.returncode}，"
        f"耗时 {result.duration_seconds:.2f} 秒")
    for line in (result.process.stdout or "").splitlines():
        log(f"{platform} {device_label} 输出: {line}")
    # stderr is an output channel, not proof that the install failed.
    failure_reason = result.failure_reason
    stderr_label = "错误输出 [stderr]" if failure_reason else "输出 [stderr]"
    for line in (result.process.stderr or "").splitlines():
        log(f"{platform} {device_label} {stderr_label}: {line}")
    if failure_reason and result.process.returncode == 0:
        log(f"{platform} {device_label} 判定安装失败：{failure_reason}")
