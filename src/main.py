import os
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Dict, Iterable, List, Optional, Set, Tuple

from config_manager import ConfigManager
from controller import (
    Inbox, Task, TaskRunner, build_install_plan, format_command_for_log, resolve_target, run_install_plan,
)
from platforms import DRIVERS, DeviceInfo, detect_devices, driver_for
from platforms.base import CollectResult, PlatformDriver
from metadata.loader import PackageLabelLoader, file_fingerprint
from packages import PACKAGE_KINDS, PackageSlot, apk_allow_test, find_packages
from ui_display import (
    format_device_ids_for_log,
    format_device_summary,
    format_device_tree_values,
    format_selected_device_summary,
    get_device_display_name,
)
from ui_layout import build_ui
from ui_styles import DEVICE_LIST_MIN_ROWS, DEVICE_LIST_MAX_ROWS, configure_window, fit_device_columns, fit_initial_window

# How often the UI thread collects background results; well below perception.
INBOX_POLL_MS = 30


def reorder_devices_for_refresh(
    devices: List[DeviceInfo],
    previous_device_ids: Set[str],
) -> Tuple[List[DeviceInfo], Set[str]]:
    new_device_ids = {device.device_id for device in devices} - previous_device_ids
    new_devices = [device for device in devices if device.device_id in new_device_ids]
    existing_devices = [device for device in devices if device.device_id not in new_device_ids]
    return new_devices + existing_devices, new_device_ids


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        configure_window(self)

        self.config_manager = ConfigManager(self._get_config_path())
        self.devices: List[DeviceInfo] = []
        self.packages: Dict[str, PackageSlot] = {kind: PackageSlot() for kind in PACKAGE_KINDS}
        self.refreshing = False
        # A failed probe means the "only" device may not be the only one.
        self.last_probe_failed = False
        # Every background result reaches this thread through the inbox.
        self.inbox = Inbox()
        self._inbox_poll = None
        # One device task (install / UDID / logs) at a time; each can be cancelled.
        self.tasks = TaskRunner(post=self.inbox.post, on_change=self._on_task_change)
        self.name_var = tk.StringVar(master=self)
        self.folder_var = tk.StringVar(master=self)
        self.install_status_var = tk.StringVar(master=self, value="就绪")
        self.device_summary_var = tk.StringVar(master=self, value=format_device_summary(self.devices))
        self.selected_device_summary_var = tk.StringVar(master=self, value="未选择设备")
        self.device_ids_before_last_refresh: Optional[Set[str]] = None
        self._latest_refresh_request_id = 0
        self._last_device_refresh_snapshot = None
        self._last_package_scan_snapshot = None
        self._package_label_loader = PackageLabelLoader(post=self.inbox.post)
        self._package_label_request = 0
        self.bind('<Destroy>', self._on_destroy, add='+')

        build_ui(self)
        self.package_combos = {"APK": self.apk_combo, "HAP": self.hap_combo}
        self._render_packages()
        fit_initial_window(self, self.device_tree)
        self._update_device_actions()
        self._poll_inbox()
        self.refresh_devices()
        self.load_last_scan_dir()

    def _get_config_path(self) -> Path:
        appdata = os.getenv("APPDATA")
        if appdata:
            base_dir = Path(appdata)
        else:
            base_dir = Path.home() / ".config"
        return base_dir / "install_new_apk_hap" / "app_config.json"

    def _append_log_entry(self, timestamp: str, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._append_log_entry(timestamp, message)

    def clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self._last_device_refresh_snapshot = None
        self._last_package_scan_snapshot = None

    def copy_log(self) -> None:
        content = self.log_text.get("1.0", "end-1c")
        self.clipboard_clear()
        if content:
            self.clipboard_append(content)

    def _device_name_mapping(self) -> Dict[str, str]:
        return self.config_manager.data.get("device_names", {})

    def _device_label(self, device_id: str) -> str:
        return get_device_display_name(device_id, self._device_name_mapping())

    def _device_labels_for_log(self, device_ids: Iterable[str]) -> str:
        return format_device_ids_for_log(device_ids, self._device_name_mapping())

    def refresh_devices(self) -> None:
        self._latest_refresh_request_id += 1
        request_id = self._latest_refresh_request_id
        self._set_refresh_state(True)
        self.tasks.background(
            detect_devices,
            lambda detection: self._apply_device_refresh_result(
                request_id, detection.devices, detection.harmony_error, detection.android_error),
            lambda error: self._apply_device_refresh_error(request_id, error),
        )

    def refresh_devices_and_packages(self) -> None:
        self.refresh_devices()
        self.scan_latest_packages()

    def _apply_device_refresh_result(
        self,
        request_id: int,
        devices: List[DeviceInfo],
        harmony_error: Optional[str] = None,
        android_error: Optional[str] = None,
    ) -> None:
        if request_id != self._latest_refresh_request_id:
            return
        self._apply_device_refresh(devices, harmony_error=harmony_error, android_error=android_error)

    def _apply_device_refresh_error(self, request_id: int, error: Exception) -> None:
        if request_id != self._latest_refresh_request_id:
            return
        self._last_device_refresh_snapshot = None
        # The kept list is stale, so its "only" device may not be the only one.
        self.last_probe_failed = True
        self.log(f"刷新设备列表失败：{error}")
        self._set_refresh_state(False)

    def _apply_device_refresh(
        self,
        devices: List[DeviceInfo],
        selection_to_restore: Optional[Iterable[str]] = None,
        summary_label: str = "设备列表已刷新",
        harmony_error: Optional[str] = None,
        android_error: Optional[str] = None,
    ) -> None:
        probe_errors = {
            platform: error
            for platform, error in (("android", android_error), ("harmony", harmony_error))
            if error
        }
        snapshot = (
            frozenset((device.device_id, device.platform, device.status) for device in devices),
            tuple(sorted(probe_errors.items())),
        )
        log_result = bool(probe_errors) or snapshot != self._last_device_refresh_snapshot or summary_label != "设备列表已刷新"
        self._last_device_refresh_snapshot = snapshot
        self.last_probe_failed = bool(probe_errors)
        current_device_ids = {device.device_id for device in devices}
        requested_selection = set(
            self.device_tree.selection()
            if selection_to_restore is None
            else selection_to_restore
        )
        if self.device_ids_before_last_refresh is None:
            ordered_devices = devices
            new_device_ids: Set[str] = set()
        else:
            ordered_devices, new_device_ids = reorder_devices_for_refresh(
                devices,
                self.device_ids_before_last_refresh,
            )
        self.device_ids_before_last_refresh = current_device_ids
        self.devices = ordered_devices
        self.device_tree.delete(*self.device_tree.get_children())
        self._update_device_tree_height()
        name_mapping: Dict[str, str] = self.config_manager.data.get("device_names", {})
        only_device_id: Optional[str] = None
        for device in self.devices:
            self.device_tree.insert(
                "",
                tk.END,
                iid=device.device_id,
                values=format_device_tree_values(device, name_mapping),
                tags=("new_device",) if device.device_id in new_device_ids else (),
            )
            if len(self.devices) == 1:
                only_device_id = device.device_id
        preserved_selection = [
            device.device_id for device in self.devices if device.device_id in requested_selection
        ]
        if preserved_selection:
            self.device_tree.selection_set(*preserved_selection)
        elif only_device_id and not probe_errors:
            # With a failed probe the "only" device may not be the only one.
            self.device_tree.selection_set(only_device_id)
        self.device_summary_var.set(format_device_summary(self.devices))
        fit_device_columns(self.device_tree)
        self.on_device_select(None)
        counts = {key: sum(device.platform == key for device in self.devices) for key in DRIVERS}
        total_count = len(self.devices)
        if probe_errors:
            if summary_label != "设备列表已刷新":
                parts = [
                    f"{driver.label} 探测失败" if key in probe_errors else f"{driver.label} {counts[key]} 台"
                    for key, driver in DRIVERS.items()
                ]
                self.log(f"{summary_label}：{'，'.join(parts)}")
            kept = [f"{driver.label} {counts[key]} 台" for key, driver in DRIVERS.items() if key not in probe_errors]
            kept_text = f"；已保留检测到的 {'、'.join(kept)}" if kept else ""
            for key, error in probe_errors.items():
                self.log(f"{DRIVERS[key].label} 设备探测失败：{error}{kept_text}")
        elif log_result and total_count == 0:
            self.log(f"{summary_label}：未检测到设备")
        elif log_result:
            per_platform = ", ".join(f"{driver.label} {counts[key]} 台" for key, driver in DRIVERS.items())
            self.log(f"{summary_label}：{per_platform}, 总计 {total_count} 台")
            if new_device_ids:
                new_device_text = self._device_labels_for_log(sorted(new_device_ids))
                self.log(f"新增设备已置顶高亮: {new_device_text}")
        self._set_refresh_state(False)

    def _update_device_tree_height(self) -> None:
        display_count = max(DEVICE_LIST_MIN_ROWS, min(len(self.devices), DEVICE_LIST_MAX_ROWS))
        self.device_tree.configure(height=display_count)

    def _update_selected_device_summary(self) -> None:
        self.selected_device_summary_var.set(format_selected_device_summary(
            self.device_tree.selection(), self.devices, self._device_name_mapping()
        ))

    def on_device_select(self, _event: Optional[tk.Event]) -> None:
        self._update_selected_device_summary()
        self._update_device_actions()
        selection = self.device_tree.selection()
        if len(selection) != 1:
            self.name_var.set("")
            return
        device_id = selection[0]
        current_name = self._device_name_mapping().get(device_id, "")
        self.name_var.set(current_name)

    def _target_device(self) -> Optional[DeviceInfo]:
        """The single device an action applies to (see controller.resolve_target)."""
        return resolve_target(self.device_tree.selection(), self.devices,
                              auto_select=not self.last_probe_failed)

    def _device_for_task(self, name: str, missing_message: str) -> Optional[DeviceInfo]:
        """Shared guards for single-device tasks: nothing running, one target."""
        if self.tasks.busy:
            self.log(f"{self.tasks.current.label}进行中，请稍候")
            return None
        device = self._target_device()
        if device is None:
            messagebox.showwarning("提示", missing_message)
            self.log(f"获取{name}失败：{missing_message}")
        return device

    def copy_selected_device_id(self) -> None:
        device = self._target_device()
        if not device:
            messagebox.showwarning("提示", "请选择一个设备复制设备码")
            self.log("复制设备码失败：请选择一个设备")
            return
        self.clipboard_clear()
        self.clipboard_append(device.device_id)
        self.log(f"已复制设备码: {self._device_label(device.device_id)}")

    def fetch_hdc_udid(self) -> None:
        device = self._device_for_task(" UDID ", "请选择一个 Harmony 设备")
        if not device:
            return
        device_id = device.device_id
        driver = driver_for(device.platform)
        if driver is None or not driver.supports_udid:
            platform_label = driver.label if driver else device.platform
            messagebox.showwarning("提示", "仅支持 NEXT 设备获取 UDID")
            self.log(f"获取 UDID 失败：设备 {self._device_label(device_id)} 为 {platform_label}，仅支持 NEXT")
            return
        task = self.tasks.start("udid", "UDID")
        self.log(f"开始获取设备 UDID: {self._device_label(device_id)}")
        self.tasks.run(
            task, lambda: driver.udid(device_id, cancel=task.cancel),
            lambda udid: self._apply_hdc_udid_result(task, device_id, udid),
            lambda error: self._apply_hdc_udid_error(task, device_id, error),
        )

    def _apply_hdc_udid_error(self, task: Task, device_id: str, error: Exception) -> None:
        if task.cancelled:
            self._end_task(task, "获取 UDID 已中止", status="已中止")
            return
        message = f"获取 UDID 失败：设备 {self._device_label(device_id)}，{error}"
        self._end_task(task, message, ok=False)
        messagebox.showwarning("提示", message)

    def _apply_hdc_udid_result(self, task: Task, device_id: str, udid: Optional[str]) -> None:
        device_label = self._device_label(device_id)
        if not udid:
            self._end_task(task, f"获取 UDID 失败：设备 {device_label} 未返回 UDID", ok=False)
            messagebox.showwarning("提示", f"未获取到设备 {device_label} 的 UDID")
            return
        self.clipboard_clear()
        self.clipboard_append(udid)
        self._end_task(task, f"已获取设备 UDID（已复制到剪贴板）: {device_label} -> {udid}")
        messagebox.showinfo("UDID", f"设备 {device_label} 的 UDID：\n{udid}\n\n已复制到剪贴板")

    def save_device_name(self) -> None:
        device = self._target_device()
        if not device:
            messagebox.showwarning("提示", "请选择一个设备进行命名")
            return
        device_id = device.device_id
        name = self.name_var.get().strip()
        self.config_manager.set_device_name(device_id, name)
        self.device_tree.set(device_id, "name", name)
        fit_device_columns(self.device_tree)
        self._update_selected_device_summary()
        self.log(f"已保存设备名称: {self._device_label(device_id)}")

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory()
        if not folder:
            self.log("已取消选择目录")
            return
        self.folder_var.set(folder)
        self.log(f"已选择安装包目录: {folder}")
        self.config_manager.set_last_scan_dir(folder)
        self.scan_latest_packages()

    def submit_folder(self, _event: Optional[tk.Event] = None) -> str:
        """Enter in the folder field: scan the typed directory, remember it if valid."""
        folder = self.folder_var.get().strip()
        if self.scan_latest_packages() and folder != self.config_manager.data.get("last_scan_dir", ""):
            self.config_manager.set_last_scan_dir(folder)
            self.log(f"已选择安装包目录: {folder}")
        return "break"

    def load_last_scan_dir(self) -> None:
        last_dir = self.config_manager.data.get("last_scan_dir", "")
        if last_dir:
            self.log(f"加载上次扫描目录: {last_dir}")
            self.folder_var.set(last_dir)
            self.scan_latest_packages()
        else:
            self.log("未找到上次扫描目录")

    def scan_latest_packages(self) -> bool:
        """Scan the folder field; False when it is empty, missing or unreadable.

        A failed scan keeps the previous packages, which are still real files.
        """
        folder = self.folder_var.get().strip()
        if not folder:
            self._last_package_scan_snapshot = None
            messagebox.showwarning("提示", "请先选择目录")
            self.log("扫描失败：未选择目录")
            return False
        directory = Path(folder)
        if not directory.is_dir():
            self._last_package_scan_snapshot = None
            messagebox.showwarning("提示", "目录不存在或不是目录")
            self.log(f"扫描失败：目录不存在或不是目录 {directory}")
            return False
        try:
            found = find_packages(directory)
            files = []
            for kind in PACKAGE_KINDS:
                for path in found[kind]:
                    stat = path.stat()
                    files.append((path, stat.st_size, stat.st_mtime_ns))
            snapshot = (directory.resolve(), tuple(files))
        except OSError as error:
            self._last_package_scan_snapshot = None
            self.log(f"扫描安装包失败：{directory}，{error}")
            messagebox.showwarning("提示", f"扫描安装包失败：{error}")
            return False
        previous_selection = self._selected_packages()
        for kind, slot in self.packages.items():
            slot.replace(found[kind])
        self._render_packages()
        selection = self._selected_packages()
        if snapshot != self._last_package_scan_snapshot or selection != previous_selection:
            names = ", ".join(f"{kind}={path.name if path else '未找到'}" for kind, path in selection.items())
            self.log(f"安装包扫描完成：{directory} · {names}")
        self._last_package_scan_snapshot = snapshot
        self._package_label_request = self._package_label_loader.submit(
            [path for slot in self.packages.values() for path in slot.candidates], self._on_package_labels)
        return True

    def _selected_packages(self) -> Dict[str, Optional[Path]]:
        return {kind: slot.selected for kind, slot in self.packages.items()}

    def _on_package_labels(self, generation: int, labels, fingerprints) -> None:
        """Metadata for the latest scan; a file changed since it was read is skipped."""
        if generation != self._package_label_request:
            return
        current_labels = {}
        for path, label in labels.items():
            try:
                if fingerprints.get(path) == file_fingerprint(path):
                    current_labels[path] = label
            except OSError:
                pass
        self._apply_package_labels(current_labels)

    def _apply_package_labels(self, labels) -> None:
        for slot in self.packages.values():
            slot.set_labels(labels)
        self._render_packages()

    def _render_packages(self) -> None:
        """Show each slot in its dropdown; the slot, not the text, holds the choice."""
        for kind, slot in self.packages.items():
            combo = self.package_combos[kind]
            if not slot.candidates:
                combo.configure(values=["未找到"], state="disabled")
                combo.set("未找到")
                continue
            combo.configure(values=slot.display_names(), state="readonly")
            combo.current(slot.index)

    def on_package_selected(self, kind: str) -> None:
        self.packages[kind].choose(self.package_combos[kind].current())

    def install_to_selected(self) -> None:
        # The primary button doubles as "stop" for whichever device task is running.
        if self.tasks.busy:
            self.cancel_current_task()
            return
        packages = self._selected_packages()
        if not any(packages.values()):
            messagebox.showwarning("提示", "未找到可安装的 APK/HAP")
            self.log("安装失败：未找到可安装的 APK/HAP")
            return
        previous_selection = set(self.device_tree.selection())
        allow_test = apk_allow_test(self.packages["APK"])
        selected_device_text = (
            self._device_labels_for_log(sorted(previous_selection))
            if previous_selection
            else "未选择（单设备时将自动选择）"
        )
        package_text = "，".join(f"{kind}={path.name if path else '未找到'}" for kind, path in packages.items())
        self.log(f"收到安装请求：设备={selected_device_text}，{package_text}")
        self.log("开始安装前设备校验")
        task = self.tasks.start("install", "安装", verb="")

        def preflight():
            started_at = time.perf_counter()
            detection = detect_devices(cancel=task.cancel)
            return detection, time.perf_counter() - started_at

        self.tasks.run(
            task, preflight,
            lambda result: self._finalize_install(
                task, result[0], previous_selection, packages, allow_test, result[1]),
            lambda error: self._apply_install_preparation_error(task, error),
        )

    def _apply_install_preparation_error(self, task: Task, error: Exception) -> None:
        self._last_device_refresh_snapshot = None
        self._end_task(task, "安装异常", status="安装异常")
        self.log(f"安装前设备校验失败：{error}")
        messagebox.showwarning("安装异常", f"安装前设备校验失败：{error}")

    def _finalize_install(
        self,
        task: Task,
        detection,
        previous_selection: Set[str],
        packages: Dict[str, Optional[Path]],
        allow_test: bool,
        validation_duration_seconds: float = 0.0,
    ) -> None:
        if task.cancelled:
            self._end_task(task, "安装已中止", status="已中止")
            return
        failed_platforms = set(detection.errors)
        if failed_platforms:
            # Only devices of a platform whose probe succeeded can be re-verified;
            # never let a failed probe redirect the install to other devices.
            verifiable_ids = {d.device_id for d in self.devices if d.platform not in failed_platforms}
            if not previous_selection or previous_selection - verifiable_ids:
                message = "\n".join(detection.errors.values())
                self._apply_install_preparation_error(task, RuntimeError(message))
                return
        self._apply_device_refresh(
            detection.devices,
            previous_selection,
            summary_label=(
                "安装前设备校验完成"
                f"（耗时 {validation_duration_seconds:.2f} 秒）"
            ),
            harmony_error=detection.harmony_error,
            android_error=detection.android_error,
        )
        current_device_ids = {device.device_id for device in self.devices}
        missing_devices = previous_selection - current_device_ids
        if missing_devices:
            missing_text = self._device_labels_for_log(sorted(missing_devices))
            messagebox.showwarning("提示", f"已选设备已断开: {missing_text}，请确认设备状态")
            self.log(f"安装提示：已选设备断开 {missing_text}")
        selection_list = [
            device.device_id
            for device in self.devices
            if device.device_id in previous_selection
        ]
        if not selection_list:
            if len(self.devices) == 1 and not failed_platforms:
                selection_list = [self.devices[0].device_id]
                self.device_tree.selection_set(selection_list[0])
                self.on_device_select(None)
                self.log(f"检测到单设备，默认安装到: {self._device_label(selection_list[0])}")
            else:
                messagebox.showwarning("提示", "请先选择设备")
                self._end_task(task, "安装失败：未选择设备", status="就绪")
                return
        # Frozen here, on the UI thread: a refresh during the install cannot
        # change which devices get which package.
        plan = build_install_plan(selection_list, self.devices, packages, self._device_label)
        self.tasks.run(
            task, lambda: run_install_plan(plan, allow_test, task.cancel, self._log_threadsafe),
            lambda outcome: self._end_task(task, outcome.status, status=outcome.status),
            lambda error: self._apply_install_error(task, error),
        )

    def _apply_install_error(self, task: Task, error: Exception) -> None:
        self.log(f"安装线程异常: {error}")
        self._end_task(task, "安装异常", status="安装异常")

    def _end_task(self, task: Task, message: str, ok: bool = True, status: Optional[str] = None) -> None:
        """Log the outcome and leave a final status; the runner then frees the slot."""
        if status is None:
            # Stop only counts when it interrupted the work; a result that
            # already arrived is reported as it is.
            status = f"{task.label}{'完成' if ok else '失败'}"
        self.install_status_var.set(status)
        self.log(message)

    def cancel_current_task(self) -> None:
        task = self.tasks.current
        if task and self.tasks.cancel():
            self._log_threadsafe(f"已请求中止{task.label}")

    def _on_task_change(self) -> None:
        """Render the device task slot: status line, primary button, busy labels."""
        task = self.tasks.current
        if task:
            self.install_status_var.set("正在中止" if task.cancelled else f"{task.label}中")
            self.install_button.config(
                state=tk.DISABLED if task.cancelled else tk.NORMAL,
                text="正在中止…" if task.cancelled else f"中止{task.label}",
            )
        else:
            # The status text is the finished task's outcome, set by _end_task.
            self.install_button.config(state=tk.NORMAL, text="安装到所选设备")
        action = task.action if task else None
        self.udid_button.config(text="获取UDID中…" if action == "udid" else "获取UDID")
        self.crash_log_button.config(text="获取崩溃日志中…" if action == "crash_log" else "获取崩溃日志")
        self.app_log_button.config(text=f"{task.label}中…" if action == "app_log" else "获取APP日志")
        self._update_device_actions()

    def _set_refresh_state(self, refreshing: bool) -> None:
        self.refreshing = refreshing
        state = tk.DISABLED if refreshing else tk.NORMAL
        self.refresh_button.config(state=state, text="刷新中…" if refreshing else "刷新设备")
        self.scan_button.config(state=state, text="刷新中…" if refreshing else "扫描最新包")
        self._update_device_actions()

    def _update_device_actions(self) -> None:
        # Same rule as the actions themselves: one selected, or the only device.
        device = self._target_device()
        driver = driver_for(device.platform) if device else None
        busy = self.refreshing or self.tasks.busy

        def state(capable: bool) -> str:
            return tk.NORMAL if capable and not busy else tk.DISABLED

        self.udid_button.config(state=state(driver is not None and driver.supports_udid))
        self.app_log_button.config(state=state(driver is not None and bool(driver.app_log_targets)))
        self.crash_log_button.config(state=state(driver is not None))

    def _get_log_output_dir(self) -> Path:
        if os.name == "nt":
            return Path("D:/")
        return Path.home() / "install_new_apk_hap_logs"

    def _log_threadsafe(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        if threading.current_thread() is threading.main_thread():
            self._append_log_entry(timestamp, message)
        else:
            self.inbox.post(lambda: self._append_log_entry(timestamp, message))

    def _poll_inbox(self) -> None:
        # Re-arm first: a failing callback must not stop later deliveries.
        self._inbox_poll = self.after(INBOX_POLL_MS, self._poll_inbox)
        self.inbox.drain()

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            self._package_label_loader.close()
            if self._inbox_poll is not None:
                self.after_cancel(self._inbox_poll)
                self._inbox_poll = None

    def fetch_crash_log(self) -> None:
        device = self._device_for_task("崩溃日志", "请选择一个设备")
        if not device:
            return
        device_id = device.device_id
        driver = driver_for(device.platform)
        if driver is None:
            messagebox.showwarning("提示", "仅支持 Android 或 Harmony 设备")
            self.log(f"获取崩溃日志失败：设备 {self._device_label(device_id)} 平台不支持")
            return
        output_dir = self._get_log_output_dir()
        task = self.tasks.start("crash_log", "崩溃日志")
        self.log(f"开始获取{driver.crash_log_description}: {self._device_label(device_id)} -> "
                 f"{driver.crash_log_destination(output_dir)}")
        self.tasks.run(
            task, lambda: driver.collect_crash_log(device_id, output_dir, cancel=task.cancel),
            lambda result: self._apply_crash_log_result(task, device_id, driver, result),
            lambda error: self._apply_log_collection_error(task, device_id, error),
        )

    def _apply_log_collection_error(self, task: Task, device_id: str, error: Exception) -> None:
        device_label = self._device_label(device_id)
        if task.cancelled:
            self._end_task(task, f"{task.label}已中止：设备 {device_label}", status="已中止")
            return
        self._end_task(task, f"{task.label}失败：设备 {device_label}\n{error}", ok=False)
        messagebox.showwarning("提示", f"{task.label}失败，设备 {device_label}: {error}")

    def _apply_crash_log_result(self, task: Task, device_id: str, driver: PlatformDriver,
                                result: CollectResult) -> None:
        device_label = self._device_label(device_id)
        process = result.process
        self.log(f"{driver.label} {device_label} 崩溃日志命令: {format_command_for_log(result.command)}")
        if process.returncode != 0:
            if task.cancelled:
                self._end_task(task, f"获取崩溃日志已中止：设备 {device_label}", status="已中止")
                return
            self._end_task(task, f"获取崩溃日志失败：设备 {device_label} 返回码 {process.returncode}\n"
                                 f"{process.stderr}", ok=False)
            messagebox.showwarning("提示", f"获取崩溃日志失败，设备 {device_label} 返回码: {process.returncode}")
            return
        if result.zip_path:
            self._end_task(task, f"获取崩溃日志成功：设备 {device_label}，共 {result.file_count} 个文件，"
                                 f"ZIP: {result.zip_path}")
            messagebox.showinfo("提示", f"已打包{driver.crash_log_description}：{result.zip_path}")
            return
        if result.appended_to:
            self._end_task(task, f"获取崩溃日志成功：设备 {device_label}，输出已追加到 {result.appended_to}")
            messagebox.showinfo("提示", f"已写入崩溃日志：{result.appended_to}")
            return
        diagnostics = (process.stderr or process.stdout or "").strip()
        self._end_task(task, f"获取崩溃日志完成但无输出：设备 {device_label}"
                             + (f"\n{diagnostics}" if diagnostics else ""), ok=False)
        messagebox.showwarning("提示", f"未获取到{driver.crash_log_description}"
                               + (f"：{diagnostics}" if diagnostics else ""))

    def fetch_qiankun_log(self) -> None:
        self._fetch_harmony_app_log("qiankun")

    def fetch_demo_log(self) -> None:
        self._fetch_harmony_app_log("demo")

    def _fetch_harmony_app_log(self, target_key: str) -> None:
        target = next(
            driver.app_log_targets[target_key] for driver in DRIVERS.values() if target_key in driver.app_log_targets
        )
        device = self._device_for_task(target.display_name, "请选择一个 Harmony 设备")
        if not device:
            return
        device_id = device.device_id
        driver = driver_for(device.platform)
        if driver is None or target_key not in driver.app_log_targets:
            messagebox.showwarning("提示", "仅支持 Harmony 设备")
            self.log(f"获取{target.display_name}失败：设备 {self._device_label(device_id)} 非 Harmony")
            return
        output_dir = self._get_log_output_dir()
        task = self.tasks.start("app_log", target.display_name)
        self.log(
            f"开始获取{target.display_name}: {self._device_label(device_id)} · "
            f"{target.remote_path} -> {output_dir}"
        )
        self.tasks.run(
            task, lambda: driver.collect_app_log(device_id, output_dir, target_key, cancel=task.cancel),
            lambda result: self._apply_harmony_app_log_result(task, device_id, target, result),
            lambda error: self._apply_log_collection_error(task, device_id, error),
        )

    def _apply_harmony_app_log_result(self, task: Task, device_id: str, target, result: CollectResult) -> None:
        command, zip_path, file_count = result.command, result.zip_path, result.file_count
        returncode, stdout, stderr = result.process.returncode, result.process.stdout, result.process.stderr
        device_label = self._device_label(device_id)
        self.log(f"{target.display_name}命令: {format_command_for_log(command)}")
        diagnostics = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
        if returncode != 0:
            if task.cancelled:
                self._end_task(task, f"获取{target.display_name}已中止：设备 {device_label}", status="已中止")
                return
            self._end_task(
                task,
                f"获取{target.display_name}失败：设备 {device_label} 返回码 {returncode}"
                + (f"\n{diagnostics}" if diagnostics else ""),
                ok=False,
            )
            messagebox.showwarning(
                "提示",
                f"获取{target.display_name}失败，设备 {device_label} 返回码: {returncode}",
            )
            return
        if not zip_path:
            self._end_task(
                task,
                f"获取{target.display_name}完成但无输出：设备 {device_label}；"
                f"远端={target.remote_path}"
                + (f"\n{diagnostics}" if diagnostics else ""),
                ok=False,
            )
            messagebox.showwarning(
                "提示",
                f"{target.display_name}未拉取到文件，请检查应用是否安装及目标目录是否存在",
            )
            return
        self._end_task(
            task,
            f"获取{target.display_name}成功：设备 {device_label}，"
            f"共 {file_count} 个文件，ZIP: {zip_path}",
        )
        messagebox.showinfo("提示", f"已打包{target.display_name}：{zip_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        from cli import run_cli
        raise SystemExit(run_cli(sys.argv[1:]))
    from ui_styles import enable_high_dpi
    enable_high_dpi()
    app = App()
    app.mainloop()
