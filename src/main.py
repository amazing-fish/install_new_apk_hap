import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from config_manager import ConfigManager
from services.device_detector import DeviceInfo, detect_devices
from services.installer import install_android, install_harmony
from services.package_scanner import find_latest_packages


class App(tk.Tk):
    _DEVICE_LIST_MAX_ROWS = 8

    def __init__(self) -> None:
        super().__init__()
        self.title("APK/HAP 安装工具")
        self.geometry("980x600")

        self.config_manager = ConfigManager(Path("config/app_config.json"))
        self.devices: List[DeviceInfo] = []
        self.latest_apk: Optional[Path] = None
        self.latest_hap: Optional[Path] = None

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
        self.device_tree.column("device_id", width=260)
        self.device_tree.column("name", width=200)
        self.device_tree.column("status", width=120)
        self.device_tree.column("platform", width=120)
        self.device_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.device_tree.bind("<<TreeviewSelect>>", self.on_device_select)

        scrollbar = ttk.Scrollbar(device_frame, orient=tk.VERTICAL, command=self.device_tree.yview)
        self.device_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        button_frame = ttk.Frame(container)
        button_frame.pack(fill=tk.X, pady=8)

        ttk.Button(button_frame, text="刷新设备", command=self.refresh_devices).pack(side=tk.LEFT)

        name_frame = ttk.Frame(container)
        name_frame.pack(fill=tk.X, pady=8)

        ttk.Label(name_frame, text="自定义名称:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(name_frame, textvariable=self.name_var, width=40)
        self.name_entry.pack(side=tk.LEFT, padx=6)
        ttk.Button(name_frame, text="保存名称", command=self.save_device_name).pack(side=tk.LEFT)

        folder_frame = ttk.LabelFrame(container, text="安装包目录")
        folder_frame.pack(fill=tk.X, pady=8)
        self.folder_var = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.folder_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=6)
        ttk.Button(folder_frame, text="选择目录", command=self.choose_folder).pack(side=tk.LEFT, padx=6)
        ttk.Button(folder_frame, text="扫描最新包", command=self.scan_latest_packages).pack(side=tk.LEFT)

        package_frame = ttk.LabelFrame(container, text="最新安装包")
        package_frame.pack(fill=tk.X, pady=8)

        self.apk_label = ttk.Label(package_frame, text="APK: 未找到")
        self.apk_label.pack(anchor=tk.W, padx=6, pady=2)
        self.hap_label = ttk.Label(package_frame, text="HAP: 未找到")
        self.hap_label.pack(anchor=tk.W, padx=6, pady=2)

        self.apk_test_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(package_frame, text="APK 需要 -t 安装", variable=self.apk_test_var).pack(
            anchor=tk.W, padx=6, pady=2
        )
        ttk.Button(package_frame, text="记住此 APK 需要 -t", command=self.remember_apk_need_t).pack(
            anchor=tk.W, padx=6, pady=2
        )

        install_frame = ttk.Frame(container)
        install_frame.pack(fill=tk.X, pady=8)
        self.install_button = ttk.Button(
            install_frame, text="安装到所选设备", command=self.install_to_selected
        )
        self.install_button.pack(side=tk.LEFT)

        log_frame = ttk.LabelFrame(container, text="日志")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=8)
        self.log_text = tk.Text(log_frame, height=12)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def refresh_devices(self) -> None:
        self.log("开始刷新设备列表")
        self.device_tree.delete(*self.device_tree.get_children())
        self.devices = detect_devices()
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
            )
            if len(self.devices) == 1:
                only_device_id = device.device_id
        if only_device_id:
            self.device_tree.selection_set(only_device_id)
            current_name = self.device_tree.set(only_device_id, "name")
            self.name_var.set(current_name)
        android_count = sum(1 for device in self.devices if device.platform == "android")
        harmony_count = sum(1 for device in self.devices if device.platform == "harmony")
        total_count = len(self.devices)
        if total_count == 0:
            self.log("设备列表已刷新：未检测到设备")
        else:
            self.log(
                "设备列表已刷新："
                f"Android {android_count} 台, Harmony {harmony_count} 台, 总计 {total_count} 台"
            )

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
        self.log(f"已保存设备名称: {device_id} -> {name}")

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
        apk_name = self.latest_apk.name if self.latest_apk else "未找到"
        hap_name = self.latest_hap.name if self.latest_hap else "未找到"
        self.apk_label.config(text=f"APK: {apk_name}")
        self.hap_label.config(text=f"HAP: {hap_name}")
        apk_needs_t = self.config_manager.data.get("apk_needs_t", [])
        self.apk_test_var.set(self.latest_apk is not None and self.latest_apk.name in apk_needs_t)
        self.log(f"已扫描最新安装包: APK={apk_name}, HAP={hap_name}")

    def remember_apk_need_t(self) -> None:
        if not self.latest_apk:
            messagebox.showwarning("提示", "未找到 APK")
            self.log("记住 APK 需要 -t 失败：未找到 APK")
            return
        self.config_manager.add_apk_need_t(self.latest_apk.name)
        self.apk_test_var.set(True)
        self.log(f"已记住 APK 需要 -t: {self.latest_apk.name}")

    def install_to_selected(self) -> None:
        selection = self.device_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择设备")
            self.log("安装失败：未选择设备")
            return
        if not self.latest_apk and not self.latest_hap:
            messagebox.showwarning("提示", "未找到可安装的 APK/HAP")
            self.log("安装失败：未找到可安装的 APK/HAP")
            return
        self._set_install_state(True)
        selection_list = list(selection)
        threading.Thread(
            target=self._install_worker,
            args=(selection_list,),
            daemon=True,
        ).start()

    def _set_install_state(self, installing: bool) -> None:
        state = tk.DISABLED if installing else tk.NORMAL
        self.install_button.config(state=state)

    def _log_threadsafe(self, message: str) -> None:
        if threading.current_thread() is threading.main_thread():
            self.log(message)
        else:
            self.after(0, self.log, message)

    def _install_worker(self, selection: List[str]) -> None:
        self._log_threadsafe(f"开始安装到所选设备: {', '.join(selection)}")
        for device_id in selection:
            device = next((d for d in self.devices if d.device_id == device_id), None)
            if not device:
                self._log_threadsafe(f"{device_id}: 设备信息未找到，跳过")
                continue
            if device.platform == "android":
                if not self.latest_apk:
                    self._log_threadsafe(f"{device_id}: 未找到 APK，跳过")
                    continue
                allow_test = self.apk_test_var.get()
                result = install_android(device_id, self.latest_apk, allow_test)
                self._log_threadsafe(f"Android {device_id} 执行命令: {' '.join(result.command)}")
                self._log_threadsafe(
                    f"Android {device_id} 安装结果: {result.process.returncode}\n"
                    f"{result.process.stdout}\n{result.process.stderr}"
                )
            else:
                if not self.latest_hap:
                    self._log_threadsafe(f"{device_id}: 未找到 HAP，跳过")
                    continue
                result = install_harmony(device_id, self.latest_hap)
                self._log_threadsafe(f"Harmony {device_id} 执行命令: {' '.join(result.command)}")
                self._log_threadsafe(
                    f"Harmony {device_id} 安装结果: {result.process.returncode}\n"
                    f"{result.process.stdout}\n{result.process.stderr}"
                )
        self.after(0, self._set_install_state, False)


if __name__ == "__main__":
    app = App()
    app.mainloop()
