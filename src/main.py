import os
import subprocess
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Iterable, List, Optional, Set, Tuple

from config_manager import ConfigManager
from services.device_detector import DeviceInfo, detect_devices, get_hdc_device_udid
from services.installer import (
    InstallResult,
    build_android_install_command,
    build_harmony_install_command,
    install_android,
    install_harmony,
    run_android_dropbox_dump,
    run_harmony_nextdemo_log_zip,
    run_harmony_recent_crash_zip,
)
from services.package_scanner import find_latest_packages
from ui_display import (
    format_device_ids_for_log,
    format_device_summary,
    format_device_tree_values,
    format_package_summary,
    format_selected_device_summary,
    get_device_display_name,
)
from ui_layout import build_ui
from ui_styles import DEVICE_LIST_MIN_ROWS, DEVICE_LIST_MAX_ROWS, configure_window, fit_device_columns, fit_initial_window


@dataclass(frozen=True)
class CrashLogTarget:
    platform: str
    output_path: Path


def reorder_devices_for_refresh(
    devices: List[DeviceInfo],
    previous_device_ids: Set[str],
) -> Tuple[List[DeviceInfo], Set[str]]:
    new_device_ids = {device.device_id for device in devices} - previous_device_ids
    new_devices = [device for device in devices if device.device_id in new_device_ids]
    existing_devices = [device for device in devices if device.device_id not in new_device_ids]
    return new_devices + existing_devices, new_device_ids


def build_crash_log_target(device: DeviceInfo, output_dir: Path) -> CrashLogTarget:
    if device.platform == "android":
        return CrashLogTarget(platform="android", output_path=output_dir / "crash.log")
    if device.platform == "harmony":
        return CrashLogTarget(platform="harmony", output_path=output_dir)
    raise ValueError(f"unsupported device platform: {device.platform}")


def format_command_for_log(command: Iterable[str]) -> str:
    return subprocess.list2cmdline(list(command))


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        configure_window(self)

        self.config_manager = ConfigManager(self._get_config_path())
        self.devices: List[DeviceInfo] = []
        self.latest_apk: Optional[Path] = None
        self.latest_hap: Optional[Path] = None
        self.apk_name_map: Dict[str, Path] = {}
        self.hap_name_map: Dict[str, Path] = {}
        self.installing = False
        self.refreshing = False
        self.install_stop_event = threading.Event()
        self.name_var = tk.StringVar(master=self)
        self.folder_var = tk.StringVar(master=self)
        self.apk_var = tk.StringVar(master=self, value="未找到")
        self.hap_var = tk.StringVar(master=self, value="未找到")
        self.apk_test_var = tk.BooleanVar(master=self, value=False)
        self.install_status_var = tk.StringVar(master=self, value="就绪")
        self.device_summary_var = tk.StringVar(master=self, value=format_device_summary(self.devices))
        self.selected_device_summary_var = tk.StringVar(master=self, value="未选择设备")
        self.package_summary_var = tk.StringVar(master=self, value=format_package_summary(None, None))
        self.udid_fetching = False
        self.crash_log_fetching = False
        self.log_operation = ""
        self.device_ids_before_last_refresh: Optional[Set[str]] = None
        self._latest_refresh_request_id = 0
        self._last_device_refresh_snapshot = None
        self._last_package_scan_snapshot = None

        build_ui(self)
        fit_initial_window(self, self.device_tree)
        self._update_device_actions()
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
        threading.Thread(target=self._refresh_devices_worker, args=(request_id,), daemon=True).start()

    def refresh_devices_and_packages(self) -> None:
        self.refresh_devices()
        self.scan_latest_packages()

    def _refresh_devices_worker(self, request_id: int) -> None:
        try:
            detection = detect_devices()
        except Exception as error:
            self.after(0, self._apply_device_refresh_error, request_id, error)
            return
        self.after(0, self._apply_device_refresh_result, request_id, detection.devices, detection.harmony_error)

    def _apply_device_refresh_result(self, request_id: int, devices: List[DeviceInfo], harmony_error: Optional[str] = None) -> None:
        if request_id != self._latest_refresh_request_id:
            return
        if harmony_error:
            self._apply_device_refresh(devices, harmony_error=harmony_error)
        else:
            self._apply_device_refresh(devices)

    def _apply_device_refresh_error(self, request_id: int, error: Exception) -> None:
        if request_id != self._latest_refresh_request_id:
            return
        self._last_device_refresh_snapshot = None
        self.log(f"刷新设备列表失败：{error}")
        self._set_refresh_state(False)

    def _apply_device_refresh(
        self,
        devices: List[DeviceInfo],
        selection_to_restore: Optional[Iterable[str]] = None,
        summary_label: str = "设备列表已刷新",
        harmony_error: Optional[str] = None,
    ) -> None:
        snapshot = (frozenset((device.device_id, device.platform, device.status) for device in devices), harmony_error)
        log_result = bool(harmony_error) or snapshot != self._last_device_refresh_snapshot or summary_label != "设备列表已刷新"
        self._last_device_refresh_snapshot = snapshot
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
        elif only_device_id:
            self.device_tree.selection_set(only_device_id)
        self.device_summary_var.set(format_device_summary(self.devices))
        fit_device_columns(self.device_tree)
        self.on_device_select(None)
        android_count = sum(1 for device in self.devices if device.platform == "android")
        harmony_count = sum(1 for device in self.devices if device.platform == "harmony")
        total_count = len(self.devices)
        if harmony_error:
            self.log(f"Harmony 设备探测失败：{harmony_error}；已保留检测到的 Android {android_count} 台")
        elif log_result and total_count == 0:
            self.log(f"{summary_label}：未检测到设备")
        elif log_result:
            self.log(
                f"{summary_label}："
                f"Android {android_count} 台, Harmony {harmony_count} 台, 总计 {total_count} 台"
            )
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

    def _single_selected_or_only_device_id(self) -> Optional[str]:
        selection = self.device_tree.selection()
        if len(selection) == 1:
            return selection[0]
        if not selection and len(self.devices) == 1:
            return self.devices[0].device_id
        return None

    def copy_selected_device_id(self) -> None:
        device_id = self._single_selected_or_only_device_id()
        if not device_id:
            messagebox.showwarning("提示", "请选择一个设备复制设备码")
            self.log("复制设备码失败：请选择一个设备")
            return
        self.clipboard_clear()
        self.clipboard_append(device_id)
        self.log(f"已复制设备码: {self._device_label(device_id)}")

    def fetch_hdc_udid(self) -> None:
        if self.udid_fetching:
            self.log("获取 UDID 中：请稍候")
            return
        selection = self.device_tree.selection()
        if len(selection) != 1:
            messagebox.showwarning("提示", "请选择一个 Harmony 设备")
            self.log("获取 UDID 失败：请选择一个 Harmony 设备")
            return
        device_id = selection[0]
        device = next((d for d in self.devices if d.device_id == device_id), None)
        device_label = self._device_label(device_id)
        if not device:
            messagebox.showwarning("提示", "设备信息不存在，请先刷新设备")
            self.log(f"获取 UDID 失败：设备 {device_label} 信息不存在")
            return
        if device.platform == "android":
            messagebox.showwarning("提示", "仅支持NEXT")
            self.log(f"获取 UDID 失败：设备 {device_label} 为 Android，仅支持 NEXT")
            return
        if device.platform != "harmony":
            messagebox.showwarning("提示", "仅支持 NEXT 设备获取 UDID")
            self.log(f"获取 UDID 失败：设备 {device_label} 平台不支持")
            return
        self._set_udid_fetch_state(True)
        self.log(f"开始获取设备 UDID: {device_label}")
        threading.Thread(target=self._fetch_hdc_udid_worker, args=(device_id,), daemon=True).start()

    def _fetch_hdc_udid_worker(self, device_id: str) -> None:
        try:
            udid = get_hdc_device_udid(device_id)
        except Exception as error:
            self.after(0, self._apply_hdc_udid_error, device_id, error)
            return
        self.after(0, self._apply_hdc_udid_result, device_id, udid)

    def _apply_hdc_udid_error(self, device_id: str, error: Exception) -> None:
        self._set_udid_fetch_state(False)
        message = f"获取 UDID 失败：设备 {self._device_label(device_id)}，{error}"
        self.log(message)
        messagebox.showwarning("提示", message)

    def _apply_hdc_udid_result(self, device_id: str, udid: Optional[str]) -> None:
        self._set_udid_fetch_state(False)
        device_label = self._device_label(device_id)
        if not udid:
            messagebox.showwarning("提示", f"未获取到设备 {device_label} 的 UDID")
            self.log(f"获取 UDID 失败：设备 {device_label} 未返回 UDID")
            return
        self.clipboard_clear()
        self.clipboard_append(udid)
        self.log(f"已获取设备 UDID（已复制到剪贴板）: {device_label} -> {udid}")
        messagebox.showinfo("UDID", f"设备 {device_label} 的 UDID：\n{udid}\n\n已复制到剪贴板")

    def save_device_name(self) -> None:
        selection = self.device_tree.selection()
        if len(selection) != 1:
            if len(self.devices) == 1:
                device_id = self.devices[0].device_id
            else:
                messagebox.showwarning("提示", "请选择一个设备进行命名")
                return
        else:
            device_id = selection[0]
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

    def load_last_scan_dir(self) -> None:
        last_dir = self.config_manager.data.get("last_scan_dir", "")
        if last_dir:
            self.log(f"加载上次扫描目录: {last_dir}")
            self.folder_var.set(last_dir)
            self.scan_latest_packages()
        else:
            self.log("未找到上次扫描目录")

    def scan_latest_packages(self) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            self._last_package_scan_snapshot = None
            messagebox.showwarning("提示", "请先选择目录")
            self.log("扫描失败：未选择目录")
            return
        directory = Path(folder)
        if not directory.is_dir():
            self._last_package_scan_snapshot = None
            messagebox.showwarning("提示", "目录不存在或不是目录")
            self.log(f"扫描失败：目录不存在或不是目录 {directory}")
            return
        try:
            package_info = find_latest_packages(directory)
            files = []
            for path in package_info.apk_candidates + package_info.hap_candidates:
                stat = path.stat()
                files.append((path, stat.st_size, stat.st_mtime_ns))
            snapshot = (directory.resolve(), tuple(files))
        except OSError as error:
            self._last_package_scan_snapshot = None
            self.log(f"扫描安装包失败：{directory}，{error}")
            messagebox.showwarning("提示", f"扫描安装包失败：{error}")
            return
        previous_selection = (self.latest_apk, self.latest_hap, self.apk_test_var.get())
        self.apk_name_map = {path.name: path for path in package_info.apk_candidates}
        self.hap_name_map = {path.name: path for path in package_info.hap_candidates}
        self.latest_apk = self._update_package_options(
            self.apk_combo, self.apk_var, package_info.apk_candidates
        )
        self.latest_hap = self._update_package_options(
            self.hap_combo, self.hap_var, package_info.hap_candidates
        )
        apk_name = self.latest_apk.name if self.latest_apk else "未找到"
        hap_name = self.latest_hap.name if self.latest_hap else "未找到"
        apk_needs_t = self.config_manager.data.get("apk_needs_t", [])
        self.apk_test_var.set(self.latest_apk is not None and self.latest_apk.name in apk_needs_t)
        self._update_package_summary()
        selection = (self.latest_apk, self.latest_hap, self.apk_test_var.get())
        if snapshot != self._last_package_scan_snapshot or selection != previous_selection:
            self.log(f"安装包扫描完成：{directory} · APK={apk_name}, HAP={hap_name}")
        self._last_package_scan_snapshot = snapshot

    def _update_package_summary(self) -> None:
        self.package_summary_var.set(format_package_summary(self.latest_apk, self.latest_hap))

    def _update_package_options(
        self,
        combo: ttk.Combobox,
        var: tk.StringVar,
        candidates: List[Path],
    ) -> Optional[Path]:
        if not candidates:
            combo.configure(values=["未找到"], state="disabled")
            var.set("未找到")
            return None
        names = [path.name for path in candidates]
        combo.configure(values=names, state="readonly")
        var.set(names[0])
        return candidates[0]

    def on_apk_selected(self, _event: tk.Event) -> None:
        selected_name = self.apk_var.get()
        self.latest_apk = self.apk_name_map.get(selected_name)
        apk_needs_t = self.config_manager.data.get("apk_needs_t", [])
        self.apk_test_var.set(self.latest_apk is not None and self.latest_apk.name in apk_needs_t)
        self._update_package_summary()

    def on_hap_selected(self, _event: tk.Event) -> None:
        selected_name = self.hap_var.get()
        self.latest_hap = self.hap_name_map.get(selected_name)
        self._update_package_summary()

    def remember_apk_need_t(self) -> None:
        if not self.latest_apk:
            messagebox.showwarning("提示", "未找到 APK")
            self.log("保存 APK 的 -t 设置失败：未找到 APK")
            return
        needs_t = bool(self.apk_test_var.get())
        self.config_manager.set_apk_need_t(self.latest_apk.name, needs_t)
        if needs_t:
            self.log(f"已记住 APK 需要 -t: {self.latest_apk.name}")
        else:
            self.log(f"已取消 APK 的 -t 记忆: {self.latest_apk.name}")

    def install_to_selected(self) -> None:
        if self.installing:
            self.request_stop_install()
            return
        if not self.latest_apk and not self.latest_hap:
            messagebox.showwarning("提示", "未找到可安装的 APK/HAP")
            self.log("安装失败：未找到可安装的 APK/HAP")
            return
        previous_selection = set(self.device_tree.selection())
        selected_apk = self.latest_apk
        selected_hap = self.latest_hap
        allow_test = self.apk_test_var.get()
        selected_device_text = (
            self._device_labels_for_log(sorted(previous_selection))
            if previous_selection
            else "未选择（单设备时将自动选择）"
        )
        apk_text = selected_apk.name if selected_apk else "未找到"
        hap_text = selected_hap.name if selected_hap else "未找到"
        self.log(
            "收到安装请求："
            f"设备={selected_device_text}，APK={apk_text}，HAP={hap_text}"
        )
        self.log("开始安装前设备校验")
        self._set_install_state(True)
        threading.Thread(
            target=self._prepare_install_worker,
            args=(previous_selection, selected_apk, selected_hap, allow_test),
            daemon=True,
        ).start()

    def _prepare_install_worker(
        self,
        previous_selection: Set[str],
        selected_apk: Optional[Path],
        selected_hap: Optional[Path],
        allow_test: bool,
    ) -> None:
        started_at = time.perf_counter()
        try:
            detection = detect_devices()
        except Exception as error:
            self.after(0, self._apply_install_preparation_error, error)
            return
        duration_seconds = time.perf_counter() - started_at
        self.after(
            0,
            self._finalize_install,
            detection.devices,
            previous_selection,
            selected_apk,
            selected_hap,
            allow_test,
            duration_seconds,
            detection.harmony_error,
        )

    def _apply_install_preparation_error(self, error: Exception) -> None:
        self._last_device_refresh_snapshot = None
        self._finish_install("安装异常")
        self.log(f"安装前设备校验失败：{error}")
        messagebox.showwarning("安装异常", f"安装前设备校验失败：{error}")

    def _finalize_install(
        self,
        devices: List[DeviceInfo],
        previous_selection: Set[str],
        selected_apk: Optional[Path],
        selected_hap: Optional[Path],
        allow_test: bool,
        validation_duration_seconds: float = 0.0,
        harmony_error: Optional[str] = None,
    ) -> None:
        if harmony_error:
            android_ids = {d.device_id for d in self.devices if d.platform == "android"}
            if previous_selection - android_ids:
                self._apply_install_preparation_error(RuntimeError(harmony_error))
                return
        self._apply_device_refresh(
            devices,
            previous_selection,
            summary_label=(
                "安装前设备校验完成"
                f"（耗时 {validation_duration_seconds:.2f} 秒）"
            ),
            harmony_error=harmony_error,
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
            if len(self.devices) == 1:
                selection_list = [self.devices[0].device_id]
                self.device_tree.selection_set(selection_list[0])
                self.on_device_select(None)
                self.log(f"检测到单设备，默认安装到: {self._device_label(selection_list[0])}")
            else:
                messagebox.showwarning("提示", "请先选择设备")
                self.log("安装失败：未选择设备")
                self.install_status_var.set("就绪")
                self._set_install_state(False)
                return
        threading.Thread(
            target=self._install_worker,
            args=(selection_list, selected_apk, selected_hap, allow_test),
            daemon=True,
        ).start()

    def _set_install_state(self, installing: bool) -> None:
        self.installing = installing
        if installing:
            self.install_stop_event.clear()
            self.install_button.config(state=tk.NORMAL, text="中止安装")
            self.install_status_var.set("安装中")
        else:
            self.install_button.config(state=tk.NORMAL, text="安装到所选设备")
            if self.install_status_var.get() == "正在中止":
                self.install_status_var.set("已中止")
            elif self.install_status_var.get() == "安装中":
                self.install_status_var.set("安装完成")
        self._update_device_actions()

    def _finish_install(self, status: str) -> None:
        self.install_status_var.set(status)
        self._set_install_state(False)
        self.log(status)

    def _set_refresh_state(self, refreshing: bool) -> None:
        self.refreshing = refreshing
        state = tk.DISABLED if refreshing else tk.NORMAL
        self.refresh_button.config(state=state, text="刷新中…" if refreshing else "刷新设备")
        self.scan_button.config(state=state, text="刷新中…" if refreshing else "扫描最新包")
        self._update_device_actions()

    def _set_udid_fetch_state(self, fetching: bool) -> None:
        self.udid_fetching = fetching
        self.udid_button.config(text="获取UDID中…" if fetching else "获取UDID")
        self._update_device_actions()

    def _set_crash_log_fetch_state(self, fetching: bool, operation: str = "崩溃日志") -> None:
        self.crash_log_fetching = fetching
        self.log_operation = operation if fetching else ""
        self.crash_log_button.config(text="获取崩溃日志中…" if fetching and operation == "崩溃日志" else "获取崩溃日志")
        self.nextdemo_log_button.config(text="获取NEXTdemo日志中…" if fetching and operation == "NEXTdemo日志" else "获取NEXTdemo日志")
        self._update_device_actions()

    def _update_device_actions(self) -> None:
        selection = self.device_tree.selection()
        device = next((d for d in self.devices if len(selection) == 1 and d.device_id == selection[0]), None)
        busy = self.refreshing or self.installing or self.udid_fetching or self.crash_log_fetching
        harmony = device is not None and device.platform == "harmony"
        supported = device is not None and device.platform in ("android", "harmony")
        self.udid_button.config(state=tk.NORMAL if harmony and not busy else tk.DISABLED)
        self.nextdemo_log_button.config(state=tk.NORMAL if harmony and not busy else tk.DISABLED)
        self.crash_log_button.config(state=tk.NORMAL if supported and not busy else tk.DISABLED)

    def _get_log_output_dir(self) -> Path:
        if os.name == "nt":
            return Path("D:/")
        return Path.home() / "install_new_apk_hap_logs"

    def _log_threadsafe(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        if threading.current_thread() is threading.main_thread():
            self._append_log_entry(timestamp, message)
        else:
            self.after(0, self._append_log_entry, timestamp, message)

    def fetch_crash_log(self) -> None:
        if self.crash_log_fetching:
            self.log("获取崩溃日志中：请稍候")
            return
        selection = self.device_tree.selection()
        if len(selection) != 1:
            messagebox.showwarning("提示", "请选择一个设备")
            self.log("获取崩溃日志失败：请选择一个设备")
            return
        device_id = selection[0]
        device = next((d for d in self.devices if d.device_id == device_id), None)
        device_label = self._device_label(device_id)
        if not device:
            messagebox.showwarning("提示", "设备信息不存在，请先刷新设备")
            self.log(f"获取崩溃日志失败：设备 {device_label} 信息不存在")
            return
        try:
            target = build_crash_log_target(device, self._get_log_output_dir())
        except ValueError:
            messagebox.showwarning("提示", "仅支持 Android 或 Harmony 设备")
            self.log(f"获取崩溃日志失败：设备 {device_label} 平台不支持")
            return
        self._set_crash_log_fetch_state(True)
        if target.platform == "android":
            self.log(f"开始获取 Android 崩溃日志: {device_label} -> {target.output_path}")
            threading.Thread(
                target=self._fetch_android_crash_log_worker,
                args=(device_id, target.output_path),
                daemon=True,
            ).start()
            return
        self.log(f"开始获取 Harmony 最近 7 天崩溃日志: {device_label} -> {target.output_path}")
        threading.Thread(
            target=self._fetch_harmony_crash_log_worker,
            args=(device_id, target.output_path),
            daemon=True,
        ).start()

    def _fetch_android_crash_log_worker(self, device_id: str, log_path: Path) -> None:
        try:
            result = run_android_dropbox_dump(device_id, log_path)
        except Exception as error:
            self.after(0, self._apply_log_collection_error, "获取崩溃日志", device_id, error)
            return
        self.after(
            0,
            self._apply_android_crash_log_result,
            device_id,
            log_path,
            result.command,
            result.process.returncode,
            result.process.stderr,
        )

    def _apply_log_collection_error(self, operation: str, device_id: str, error: Exception) -> None:
        self._set_crash_log_fetch_state(False)
        device_label = self._device_label(device_id)
        messagebox.showwarning("提示", f"{operation}失败，设备 {device_label}: {error}")
        self.log(f"{operation}失败：设备 {device_label}\n{error}")

    def _apply_android_crash_log_result(
        self,
        device_id: str,
        log_path: Path,
        command: List[str],
        returncode: int,
        stderr: str,
    ) -> None:
        self._set_crash_log_fetch_state(False)
        device_label = self._device_label(device_id)
        self.log(f"Android {device_label} 崩溃日志命令: {' '.join(command)}")
        if returncode != 0:
            messagebox.showwarning("提示", f"获取崩溃日志失败，设备 {device_label} 返回码: {returncode}")
            self.log(f"获取崩溃日志失败：设备 {device_label} 返回码 {returncode}\n{stderr}")
            return
        messagebox.showinfo("提示", f"已写入崩溃日志：{log_path}")
        self.log(f"获取崩溃日志成功：设备 {device_label}，输出已追加到 {log_path}")

    def _fetch_harmony_crash_log_worker(self, device_id: str, output_dir: Path) -> None:
        try:
            result = run_harmony_recent_crash_zip(device_id, output_dir, days=7)
        except Exception as error:
            self.after(0, self._apply_log_collection_error, "获取崩溃日志", device_id, error)
            return
        self.after(
            0,
            self._apply_harmony_crash_log_result,
            device_id,
            output_dir,
            result.command,
            result.process.returncode,
            result.process.stdout,
            result.process.stderr,
            result.zip_path,
            result.file_count,
        )

    def _apply_harmony_crash_log_result(
        self,
        device_id: str,
        output_dir: Path,
        command: List[str],
        returncode: int,
        stdout: str,
        stderr: str,
        zip_path: Optional[Path],
        file_count: int,
    ) -> None:
        self._set_crash_log_fetch_state(False)
        device_label = self._device_label(device_id)
        self.log(f"Harmony {device_label} 崩溃日志命令: {' '.join(command)}")
        if returncode != 0:
            messagebox.showwarning("提示", f"获取崩溃日志失败，设备 {device_label} 返回码: {returncode}")
            self.log(f"获取崩溃日志失败：设备 {device_label} 返回码 {returncode}\n{stderr}")
            return
        if not zip_path:
            messagebox.showwarning("提示", f"最近 7 天未打包到 crash 日志，请检查设备路径（目录：{output_dir}）")
            self.log(f"获取崩溃日志完成但无输出：设备 {device_label}\n{stderr or stdout}")
            return
        messagebox.showinfo("提示", f"已打包最近 7 天崩溃日志：{zip_path}")
        self.log(f"获取崩溃日志成功：设备 {device_label}，共 {file_count} 个文件，ZIP: {zip_path}")

    def fetch_nextdemo_log(self) -> None:
        if self.crash_log_fetching:
            self.log("获取NEXTdemo日志中：请稍候")
            return
        selection = self.device_tree.selection()
        if len(selection) != 1:
            messagebox.showwarning("提示", "请选择一个 Harmony 设备")
            self.log("获取NEXTdemo日志失败：请选择一个 Harmony 设备")
            return
        device_id = selection[0]
        device = next((d for d in self.devices if d.device_id == device_id), None)
        device_label = self._device_label(device_id)
        if not device:
            messagebox.showwarning("提示", "设备信息不存在，请先刷新设备")
            self.log(f"获取NEXTdemo日志失败：设备 {device_label} 信息不存在")
            return
        if device.platform != "harmony":
            messagebox.showwarning("提示", "仅支持 Harmony 设备")
            self.log(f"获取NEXTdemo日志失败：设备 {device_label} 非 Harmony")
            return
        output_dir = self._get_log_output_dir()
        self._set_crash_log_fetch_state(True, "NEXTdemo日志")
        self.log(f"开始获取NEXTdemo日志: {device_label} -> {output_dir}")
        threading.Thread(
            target=self._fetch_nextdemo_log_worker,
            args=(device_id, output_dir),
            daemon=True,
        ).start()

    def _fetch_nextdemo_log_worker(self, device_id: str, output_dir: Path) -> None:
        try:
            result = run_harmony_nextdemo_log_zip(device_id, output_dir)
        except Exception as error:
            self.after(0, self._apply_log_collection_error, "获取NEXTdemo日志", device_id, error)
            return
        self.after(
            0,
            self._apply_nextdemo_log_result,
            device_id,
            result.command,
            result.process.returncode,
            result.process.stdout,
            result.process.stderr,
            result.zip_path,
            result.file_count,
        )

    def _apply_nextdemo_log_result(
        self,
        device_id: str,
        command: List[str],
        returncode: int,
        stdout: str,
        stderr: str,
        zip_path: Optional[Path],
        file_count: int,
    ) -> None:
        self._set_crash_log_fetch_state(False)
        device_label = self._device_label(device_id)
        self.log(f"NEXTdemo 日志命令: {' '.join(command)}")
        if returncode != 0:
            messagebox.showwarning("提示", f"获取NEXTdemo日志失败，设备 {device_label} 返回码: {returncode}")
            self.log(f"获取NEXTdemo日志失败：设备 {device_label} 返回码 {returncode}\n{stderr}")
            return
        if not zip_path:
            messagebox.showwarning("提示", "未找到 haps/entry/files/log-ads 或无可拉取文件")
            self.log(f"获取NEXTdemo日志完成但无输出：设备 {device_label}\n{stderr or stdout}")
            return
        messagebox.showinfo("提示", f"已打包NEXTdemo日志：{zip_path}")
        self.log(f"获取NEXTdemo日志成功：设备 {device_label}，共 {file_count} 个文件，ZIP: {zip_path}")

    def _install_worker(
        self,
        selection: List[str],
        selected_apk: Optional[Path],
        selected_hap: Optional[Path],
        allow_test: bool,
    ) -> None:
        self._log_threadsafe(f"开始安装到所选设备: {self._device_labels_for_log(selection)}")
        cancelled_by_user = False
        install_failed = False
        failed_commands = 0
        skipped_targets = 0
        try:
            for device_id in selection:
                device_label = self._device_label(device_id)
                if self.install_stop_event.is_set():
                    cancelled_by_user = True
                    self._log_threadsafe("安装已中止")
                    break
                device = next((d for d in self.devices if d.device_id == device_id), None)
                if not device:
                    skipped_targets += 1
                    self._log_threadsafe(f"{device_label}: 设备信息未找到，跳过")
                    continue
                if device.platform == "android":
                    if not selected_apk:
                        skipped_targets += 1
                        self._log_threadsafe(f"{device_label}: 未找到 APK，跳过")
                        continue
                    command = build_android_install_command(
                        device_id,
                        selected_apk,
                        allow_test,
                    )
                    self._log_threadsafe(
                        f"Android {device_label} 开始执行命令: "
                        f"{format_command_for_log(command)}"
                    )
                    result = install_android(
                        device_id,
                        selected_apk,
                        allow_test,
                        self.install_stop_event,
                    )
                    self._log_install_result("Android", device_label, result)
                else:
                    if not selected_hap:
                        skipped_targets += 1
                        self._log_threadsafe(f"{device_label}: 未找到 HAP，跳过")
                        continue
                    command = build_harmony_install_command(device_id, selected_hap)
                    self._log_threadsafe(
                        f"Harmony {device_label} 开始执行命令: "
                        f"{format_command_for_log(command)}"
                    )
                    result = install_harmony(device_id, selected_hap, self.install_stop_event, hdc_executable=command[0])
                    self._log_install_result("Harmony", device_label, result)
                if self.install_stop_event.is_set():
                    cancelled_by_user = True
                    self._log_threadsafe(f"{device_label}: 安装已中止")
                    break
                if result.process.returncode != 0:
                    failed_commands += 1
        except Exception as error:
            install_failed = True
            self._log_threadsafe(f"安装线程异常: {error}")
        finally:
            if install_failed:
                status = "安装异常"
            elif cancelled_by_user:
                status = "已中止"
            elif failed_commands:
                status = "安装失败"
            elif skipped_targets:
                status = "安装未完成"
            else:
                status = "安装完成"
            self.after(0, self._finish_install, status)

    def _log_install_result(
        self,
        platform: str,
        device_label: str,
        result: InstallResult,
    ) -> None:
        self._log_threadsafe(
            f"{platform} {device_label} 安装结果: {result.process.returncode}，"
            f"耗时 {result.duration_seconds:.2f} 秒"
        )
        for line in result.process.stdout.splitlines():
            self._log_threadsafe(f"{platform} {device_label} 输出: {line}")
        for line in result.process.stderr.splitlines():
            self._log_threadsafe(f"{platform} {device_label} 错误输出: {line}")

    def request_stop_install(self) -> None:
        if not self.installing:
            return
        self.install_stop_event.set()
        self.install_button.config(state=tk.DISABLED, text="正在中止…")
        self.install_status_var.set("正在中止")
        self._log_threadsafe("已请求中止安装")


if __name__ == "__main__":
    app = App()
    app.mainloop()
