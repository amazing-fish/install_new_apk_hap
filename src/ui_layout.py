"""Build the existing Tk interface using App-owned variables and callbacks.

Call once, on the Tk thread, after initializing the variables. Builders attach
widget references used by App's event handlers; they never start tasks, load
configuration, or replace variables. Layout-only changes stay in this module.
"""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ui_display import DEVICE_DISPLAY_COLUMNS
from ui_styles import PACKAGE_COMBO_VISIBLE_ROWS, SUMMARY_WRAP_LENGTH, configure_device_tree

if TYPE_CHECKING:
    from main import App


def build_ui(app: "App") -> None:
    _build_status_bar(app)
    container = ttk.Frame(app)
    container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
    _build_device_section(app, container)
    _build_package_section(app, container)
    _build_execution_section(app, container)
    _build_log_section(app, container)


def _build_status_bar(app: "App") -> None:
    status_bar = ttk.Frame(app)
    status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 6))
    ttk.Label(status_bar, textvariable=app.install_status_var).pack(side=tk.LEFT, padx=(0, 8))
    app.status_selection_label = _add_summary_label(
        status_bar, app.selected_device_summary_var
    )


def _build_device_section(app: "App", container: ttk.Frame) -> None:
    device_frame = ttk.LabelFrame(container, text="设备列表")
    device_frame.pack(fill=tk.BOTH, expand=False)
    device_heading = ttk.Frame(device_frame)
    ttk.Label(device_heading, text="设备列表").pack(side=tk.LEFT, padx=(0, 8))
    ttk.Label(device_heading, textvariable=app.device_summary_var).pack(side=tk.LEFT)
    device_frame.configure(labelwidget=device_heading)

    columns = ("device_id", "name", "status", "platform")
    app.device_tree = ttk.Treeview(
        device_frame,
        columns=columns,
        displaycolumns=DEVICE_DISPLAY_COLUMNS,
        show="headings",
        selectmode="extended",
        height=1,
    )
    configure_device_tree(app.device_tree)
    app.device_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    app.device_tree.bind("<<TreeviewSelect>>", app.on_device_select)

    scrollbar = ttk.Scrollbar(device_frame, orient=tk.VERTICAL, command=app.device_tree.yview)
    app.device_tree.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    button_frame = ttk.Frame(container)
    button_frame.pack(fill=tk.X, pady=3)

    app.refresh_button = ttk.Button(
        button_frame,
        text="刷新设备",
        command=app.refresh_devices_and_packages,
    )
    app.refresh_button.pack(side=tk.LEFT)
    app.udid_button = ttk.Button(button_frame, text="获取UDID", command=app.fetch_hdc_udid)
    app.udid_button.pack(side=tk.LEFT, padx=6)
    app.crash_log_button = ttk.Button(button_frame, text="获取崩溃日志", command=app.fetch_crash_log)
    app.crash_log_button.pack(side=tk.LEFT)
    app.nextdemo_log_button = ttk.Button(
        button_frame,
        text="获取NEXTdemo日志",
        command=app.fetch_nextdemo_log,
    )
    app.nextdemo_log_button.pack(side=tk.LEFT, padx=6)

    name_frame = ttk.Frame(container)
    name_frame.pack(fill=tk.X, pady=3)
    name_frame.columnconfigure(1, weight=1)

    ttk.Label(name_frame, text="自定义名称:").grid(row=0, column=0)
    app.name_entry = ttk.Entry(name_frame, textvariable=app.name_var)
    app.name_entry.grid(row=0, column=1, sticky=tk.EW, padx=6)
    ttk.Button(name_frame, text="保存名称", command=app.save_device_name).grid(
        row=0,
        column=2,
    )
    ttk.Button(name_frame, text="复制设备码", command=app.copy_selected_device_id).grid(
        row=0,
        column=3,
        padx=(6, 0),
    )


def _build_package_section(app: "App", container: ttk.Frame) -> None:
    folder_frame = ttk.LabelFrame(container, text="安装包目录")
    folder_frame.pack(fill=tk.X, pady=3)
    ttk.Entry(folder_frame, textvariable=app.folder_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=6)
    ttk.Button(folder_frame, text="选择目录", command=app.choose_folder).pack(side=tk.LEFT, padx=6)
    app.scan_button = ttk.Button(
        folder_frame,
        text="扫描最新包",
        command=app.refresh_devices_and_packages,
    )
    app.scan_button.pack(side=tk.LEFT)

    package_frame = ttk.LabelFrame(container, text="最新安装包")
    package_frame.pack(fill=tk.X, pady=3)

    apk_row = ttk.Frame(package_frame)
    apk_row.pack(fill=tk.X, padx=6, pady=2)
    ttk.Label(apk_row, text="APK:").pack(side=tk.LEFT)
    app.apk_combo = ttk.Combobox(
        apk_row,
        textvariable=app.apk_var,
        state="disabled",
        height=PACKAGE_COMBO_VISIBLE_ROWS,
    )
    app.apk_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
    app.apk_combo.bind("<<ComboboxSelected>>", app.on_apk_selected)

    hap_row = ttk.Frame(package_frame)
    hap_row.pack(fill=tk.X, padx=6, pady=2)
    ttk.Label(hap_row, text="HAP:").pack(side=tk.LEFT)
    app.hap_combo = ttk.Combobox(
        hap_row,
        textvariable=app.hap_var,
        state="disabled",
        height=PACKAGE_COMBO_VISIBLE_ROWS,
    )
    app.hap_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
    app.hap_combo.bind("<<ComboboxSelected>>", app.on_hap_selected)

    ttk.Checkbutton(package_frame, text="APK 需要 -t 安装", variable=app.apk_test_var).pack(
        anchor=tk.W, padx=6, pady=2
    )
    ttk.Button(package_frame, text="保存此 APK 的 -t 设置", command=app.remember_apk_need_t).pack(
        anchor=tk.W, padx=6, pady=2
    )
    _add_summary_label(package_frame, app.package_summary_var)


def _build_execution_section(app: "App", container: ttk.Frame) -> None:
    app.execution_selection_label = _add_summary_label(
        container, app.selected_device_summary_var
    )
    install_frame = ttk.Frame(container)
    install_frame.pack(fill=tk.X, pady=3)
    app.install_button = ttk.Button(
        install_frame, text="安装到所选设备", command=app.install_to_selected
    )
    app.install_button.pack(side=tk.LEFT)
    ttk.Label(install_frame, text="状态:").pack(side=tk.LEFT, padx=(12, 4))
    ttk.Label(install_frame, textvariable=app.install_status_var).pack(side=tk.LEFT)


def _build_log_section(app: "App", container: ttk.Frame) -> None:
    log_frame = ttk.LabelFrame(container, text="日志")
    log_frame.pack(fill=tk.BOTH, expand=True, pady=3)
    log_button_frame = ttk.Frame(log_frame)
    log_button_frame.pack(fill=tk.X, padx=6, pady=(6, 0))
    ttk.Button(log_button_frame, text="复制日志", command=app.copy_log).pack(side=tk.LEFT)
    ttk.Button(log_button_frame, text="清空日志", command=app.clear_log).pack(side=tk.LEFT, padx=6)
    app.log_text = tk.Text(log_frame, height=12)
    app.log_text.pack(fill=tk.BOTH, expand=True)
    app.log_text.configure(state=tk.DISABLED)


def _add_summary_label(parent: ttk.Frame, variable: tk.StringVar) -> ttk.Label:
    label = ttk.Label(parent, textvariable=variable, wraplength=SUMMARY_WRAP_LENGTH)
    label.pack(fill=tk.X, pady=2)
    label.bind("<Configure>", lambda event: label.configure(wraplength=max(1, event.width - 4)))
    return label
