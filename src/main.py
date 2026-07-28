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


def get_device_display_name(device_id: str, name_mapping: Dict[str, str]) -> str:
    name = name_mapping.get(device_id, "").strip()
    return name or device_id


def format_device_ids_for_log(device_ids: Iterable[str], name_mapping: Dict[str, str]) -> str:
    return "，".join(get_device_display_name(device_id, name_mapping) for device_id in device_ids)


def format_command_for_log(command: Iterable[str]) -> str:
    return subprocess.list2cmdline(list(command))


class App(tk.Tk):
    _DEVICE_LIST_MAX_ROWS = 8
    _PACKAGE_COMBO_VISIBLE_ROWS = 10

    def __init__(self) -> None:
        super().__init__()
        self.title("APK/HAP 安装工具")
        self.geometry("500x600")

        self.config_manager = ConfigManager(self._get_config_path())
        self.devices: List[DeviceInfo] = []
        self.latest_apk: Optional[Path] = None
        self.latest_hap: Optional[Path] = None
        self.apk_name_map: Dict[str, Path] = {}
        self.hap_name_map: Dict[str, Path] = {}
        self.installing = False
        self.install_stop_event = threading.Event()
        self.install_status_var = tk.StringVar(value="就绪")
        self.udid_fetching = False
        self.crash_log_fetching = False
        self.device_ids_before_last_refresh: Optional[Set[str]] = None
        self._latest_refresh_request_id = 0

        self._build_ui()
        self.refresh_devices()
        self.load_last_scan_dir()

    def _build_ui(self) -> None:
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        device_frame = ttk.LabelFrame(container, text="设备列表")
        device_frame.pack(fill=tk.BOTH, expand=False)

        columns = ("device_id", "name", "status", "platform")
        self.device_tree = ttk.Treeview(
            device_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=1,
        )
        self.device_tree.heading("device_id", text="设备码")
        self.device_tree.heading("name", text="名称")
        self.device_tree.heading("status", text="状态")
        self.device_tree.heading("platform", text="平台")
        self.device_tree.column("device_id", width=130)
        self.device_tree.column("name", width=100)
        self.device_tree.column("status", width=120)
        self.device_tree.column("platform", width=120)
        self.device_tree.tag_configure("new_device", background="#DFF6DD")
        self.device_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.device_tree.bind("<<TreeviewSelect>>", self.on_device_select)

        scrollbar = ttk.Scrollbar(device_frame, orient=tk.VERTICAL, command=self.device_tree.yview)
        self.device_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        button_frame = ttk.Frame(container)
        button_frame.pack(fill=tk.X, pady=8)

        self.refresh_button = ttk.Button(
            button_frame,
            text="刷新设备",
            command=self.refresh_devices_and_packages,
        )
        self.refresh_button.pack(side=tk.LEFT)
        self.udid_button = ttk.Button(button_frame, text="获取UDID", command=self.fetch_hdc_udid)
        self.udid_button.pack(side=tk.LEFT, padx=6)
        self.crash_log_button = ttk.Button(button_frame, text="获取崩溃日志", command=self.fetch_crash_log)
        self.crash_log_button.pack(side=tk.LEFT)
        self.nextdemo_log_button = ttk.Button(
            button_frame,
            text="获取NEXTdemo日志",
            command=self.fetch_nextdemo_log,
        )
        self.nextdemo_log_button.pack(side=tk.LEFT, padx=6)

        name_frame = ttk.Frame(container)
        name_frame.pack(fill=tk.X, pady=8)
        name_frame.columnconfigure(1, weight=1)

        ttk.Label(name_frame, text="自定义名称:").grid(row=0, column=0)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(name_frame, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=1, sticky=tk.EW, padx=6)
        ttk.Button(name_frame, text="保存名称", command=self.save_device_name).grid(
            row=0,
            column=2,
        )
        ttk.Button(name_frame, text="复制设备码", command=self.copy_selected_device_id).grid(
            row=0,
            column=3,
            padx=(6, 0),
        )

        folder_frame = ttk.LabelFrame(container, text="安装包目录")
        folder_frame.pack(fill=tk.X, pady=8)
        self.folder_var = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.folder_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=6)
        ttk.Button(folder_frame, text="选择目录", command=self.choose_folder).pack(side=tk.LEFT, padx=6)
        self.scan_button = ttk.Button(
            folder_frame,
            text="扫描最新包",
            command=self.refresh_devices_and_packages,
        )
        self.scan_button.pack(side=tk.LEFT)

        package_frame = ttk.LabelFrame(container, text="最新安装包")
        package_frame.pack(fill=tk.X, pady=8)

        apk_row = ttk.Frame(package_frame)
        apk_row.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(apk_row, text="APK:").pack(side=tk.LEFT)
        self.apk_var = tk.StringVar(value="未找到")
        self.apk_combo = ttk.Combobox(
            apk_row,
            textvariable=self.apk_var,
            state="disabled",
            height=self._PACKAGE_COMBO_VISIBLE_ROWS,
        )
        self.apk_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.apk_combo.bind("<<ComboboxSelected>>", self.on_apk_selected)

        hap_row = ttk.Frame(package_frame)
        hap_row.pack(fill=tk.X, padx=6, pady=2)
        ttk.Label(hap_row, text="HAP:").pack(side=tk.LEFT)
        self.hap_var = tk.StringVar(value="未找到")
        self.hap_combo = ttk.Combobox(
            hap_row,
            textvariable=self.hap_var,
            state="disabled",
            height=self._PACKAGE_COMBO_VISIBLE_ROWS,
        )
        self.hap_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.hap_combo.bind("<<ComboboxSelected>>", self.on_hap_selected)

        self.apk_test_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(package_frame, text="APK 需要 -t 安装", variable=self.apk_test_var).pack(
            anchor=tk.W, padx=6, pady=2
        )
        ttk.Button(package_frame, text="保存此 APK 的 -t 设置", command=self.remember_apk_need_t).pack(
            anchor=tk.W, padx=6, pady=2
        )

        install_frame = ttk.Frame(container)
        install_frame.pack(fill=tk.X, pady=8)
        self.install_button = ttk.Button(
            install_frame, text="安装到所选设备", command=self.install_to_selected
        )
        self.install_button.pack(side=tk.LEFT)
        ttk.Label(install_frame, text="状态:").pack(side=tk.LEFT, padx=(12, 4))
        ttk.Label(install_frame, textvariable=self.install_status_var).pack(side=tk.LEFT)

        log_frame = ttk.LabelFrame(container, text="日志")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=8)
        log_button_frame = ttk.Frame(log_frame)
        log_button_frame.pack(fill=tk.X, padx=6, pady=(6, 0))
        ttk.Button(log_button_frame, text="复制日志", command=self.copy_log).pack(side=tk.LEFT)
        ttk.Button(log_button_frame, text="清空日志", command=self.clear_log).pack(side=tk.LEFT, padx=6)
        self.log_text = tk.Text(log_frame, height=12)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.configure(state=tk.DISABLED)

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
        self._log_threadsafe("开始刷新设备列表")
        threading.Thread(target=self._refresh_devices_worker, args=(request_id,), daemon=True).start()

    def refresh_devices_and_packages(self) -> None:
        self.refresh_devices()
        self.scan_latest_packages()

    def _refresh_devices_worker(self, request_id: int) -> None:
        try:
            devices = detect_devices()
        except Exception as error:
            self.after(0, self._apply_device_refresh_error, request_id, error)
            return
        self.after(0, self._apply_device_refresh_result, request_id, devices)

    def _apply_device_refresh_result(self, request_id: int, devices: List[DeviceInfo]) -> None:
        if request_id != self._latest_refresh_request_id:
            return
        self._apply_device_refresh(devices)

    def _apply_device_refresh_error(self, request_id: int, error: Exception) -> None:
        if request_id != self._latest_refresh_request_id:
            return
        self.log(f"刷新设备列表失败：{error}")
        self._set_refresh_state(False)

    def _apply_device_refresh(
        self,
        devices: List[DeviceInfo],
        selection_to_restore: Optional[Iterable[str]] = None,
        summary_label: str = "设备列表已刷新",
    ) -> None:
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
            name = name_mapping.get(device.device_id, "")
            self.device_tree.insert(
                "",
                tk.END,
                iid=device.device_id,
                values=(device.device_id, name, device.status, device.platform),
                tags=("new_device",) if device.device_id in new_device_ids else (),
            )
            if len(self.devices) == 1:
                only_device_id = device.device_id
        preserved_selection = [
            device.device_id for device in self.devices if device.device_id in requested_selection
        ]
        if preserved_selection:
            self.device_tree.selection_set(*preserved_selection)
            if len(preserved_selection) == 1:
                current_name = self.device_tree.set(preserved_selection[0], "name")
                self.name_var.set(current_name)
            else:
                self.name_var.set("")
        elif only_device_id:
            self.device_tree.selection_set(only_device_id)
            current_name = self.device_tree.set(only_device_id, "name")
            self.name_var.set(current_name)
        android_count = sum(1 for device in self.devices if device.platform == "android")
        harmony_count = sum(1 for device in self.devices if device.platform == "harmony")
        total_count = len(self.devices)
        if total_count == 0:
            self.log(f"{summary_label}：未检测到设备")
        else:
            self.log(
                f"{summary_label}："
                f"Android {android_count} 台, Harmony {harmony_count} 台, 总计 {total_count} 台"
            )
            if new_device_ids:
                new_device_text = self._device_labels_for_log(sorted(new_device_ids))
                self.log(f"新增设备已置顶高亮: {new_device_text}")
        self._set_refresh_state(False)

    def _update_device_tree_height(self) -> None:
        display_count = max(1, min(len(self.devices), self._DEVICE_LIST_MAX_ROWS))
        self.device_tree.configure(height=display_count)

    def on_device_select(self, _event: tk.Event) -> None:
        selection = self.device_tree.selection()
        if len(selection) != 1:
            self.name_var.set("")
            return
        device_id = selection[0]
        current_name = self.device_tree.set(device_id, "name")
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
        udid = get_hdc_device_udid(device_id)
        self.after(0, self._apply_hdc_udid_result, device_id, udid)

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
            messagebox.showwarning("提示", "请先选择目录")
            self.log("扫描失败：未选择目录")
            return
        directory = Path(folder)
        if not directory.exists():
            messagebox.showwarning("提示", "目录不存在")
            self.log(f"扫描失败：目录不存在 {directory}")
            return
        self.log(f"开始扫描最新安装包: {directory}")
        package_info = find_latest_packages(directory)
        self.latest_apk = package_info.apk_path
        self.latest_hap = package_info.hap_path
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
        self.log(f"已扫描最新安装包: APK={apk_name}, HAP={hap_name}")

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

    def on_hap_selected(self, _event: tk.Event) -> None:
        selected_name = self.hap_var.get()
        self.latest_hap = self.hap_name_map.get(selected_name)

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
        devices = detect_devices()
        duration_seconds = time.perf_counter() - started_at
        self.after(
            0,
            self._finalize_install,
            devices,
            previous_selection,
            selected_apk,
            selected_hap,
            allow_test,
            duration_seconds,
        )

    def _finalize_install(
        self,
        devices: List[DeviceInfo],
        previous_selection: Set[str],
        selected_apk: Optional[Path],
        selected_hap: Optional[Path],
        allow_test: bool,
        validation_duration_seconds: float = 0.0,
    ) -> None:
        self._apply_device_refresh(
            devices,
            previous_selection,
            summary_label=(
                "安装前设备校验完成"
                f"（耗时 {validation_duration_seconds:.2f} 秒）"
            ),
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
                current_name = self.device_tree.set(selection_list[0], "name")
                self.name_var.set(current_name)
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
            self.install_button.config(state=tk.NORMAL, text="中止下载")
            self.install_status_var.set("安装中")
        else:
            self.install_button.config(state=tk.NORMAL, text="安装到所选设备")
            if self.install_status_var.get() == "正在中止":
                self.install_status_var.set("已中止")
            elif self.install_status_var.get() == "安装中":
                self.install_status_var.set("安装完成")

    def _set_refresh_state(self, refreshing: bool) -> None:
        state = tk.DISABLED if refreshing else tk.NORMAL
        self.refresh_button.config(state=state)
        self.scan_button.config(state=state)

    def _set_udid_fetch_state(self, fetching: bool) -> None:
        self.udid_fetching = fetching
        state = tk.DISABLED if fetching else tk.NORMAL
        self.udid_button.config(state=state)

    def _set_crash_log_fetch_state(self, fetching: bool) -> None:
        self.crash_log_fetching = fetching
        state = tk.DISABLED if fetching else tk.NORMAL
        self.crash_log_button.config(state=state)
        self.nextdemo_log_button.config(state=state)

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
        self._set_crash_log_fetch_state(True)
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
        try:
            for device_id in selection:
                device_label = self._device_label(device_id)
                if self.install_stop_event.is_set():
                    cancelled_by_user = True
                    self._log_threadsafe("安装已中止")
                    break
                device = next((d for d in self.devices if d.device_id == device_id), None)
                if not device:
                    self._log_threadsafe(f"{device_label}: 设备信息未找到，跳过")
                    continue
                if device.platform == "android":
                    if not selected_apk:
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
                        self._log_threadsafe(f"{device_label}: 未找到 HAP，跳过")
                        continue
                    command = build_harmony_install_command(device_id, selected_hap)
                    self._log_threadsafe(
                        f"Harmony {device_label} 开始执行命令: "
                        f"{format_command_for_log(command)}"
                    )
                    result = install_harmony(device_id, selected_hap, self.install_stop_event)
                    self._log_install_result("Harmony", device_label, result)
                if self.install_stop_event.is_set():
                    cancelled_by_user = True
                    self._log_threadsafe(f"{device_label}: 安装已中止")
                    break
        except Exception as error:
            install_failed = True
            self._log_threadsafe(f"安装线程异常: {error}")
        finally:
            if install_failed:
                self.after(0, self.install_status_var.set, "安装异常")
            elif cancelled_by_user:
                self.after(0, self.install_status_var.set, "正在中止")
            self.after(0, self._set_install_state, False)

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
        self.install_button.config(state=tk.DISABLED)
        self.install_status_var.set("正在中止")
        self._log_threadsafe("已请求中止安装")


if __name__ == "__main__":
    app = App()
    app.mainloop()
