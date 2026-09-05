"""One-time UI assembly using App-owned variables and callbacks."""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ui_display import DEVICE_DISPLAY_COLUMNS
from ui_styles import PACKAGE_COMBO_VISIBLE_ROWS, SUMMARY_WRAP_LENGTH, configure_device_tree
from ui_widgets import ActionRow, ScrollableArea

if TYPE_CHECKING:
    from main import App


def build_ui(app: 'App') -> None:
    _build_execution_bar(app)
    app.scroll_area = ScrollableArea(app)
    app.scroll_area.pack(fill=tk.BOTH, expand=True)
    container = app.scroll_area.content
    _build_device_section(app, container)
    _build_package_section(app, container)
    selection = _section(container, '03  确认安装目标')
    app.execution_selection_label = _add_summary_label(selection, app.selected_device_summary_var)
    _add_summary_label(selection, app.package_summary_var)
    _build_log_section(app, container)


def _section(parent, title):
    frame = ttk.LabelFrame(parent, text=title, padding=8)
    frame.pack(fill=tk.X, pady=(0, 10))
    return frame


def _build_execution_bar(app):
    bar = ttk.Frame(app, padding=(12, 8))
    bar.pack(side=tk.BOTTOM, fill=tk.X)
    bar.columnconfigure(0, weight=1)
    # Compact mirror; the full, wrapping summary is in the scrollable section.
    app.status_selection_label = ttk.Label(bar, textvariable=app.selected_device_summary_var, width=1)
    app.status_selection_label.grid(row=0, column=0, sticky=tk.EW, padx=(0, 8))
    app.install_button = ttk.Button(bar, text='安装到所选设备', command=app.install_to_selected)
    app.install_button.grid(row=0, column=1, rowspan=2, sticky=tk.E)
    ttk.Label(bar, textvariable=app.install_status_var).grid(row=1, column=0, sticky=tk.W)


def _build_device_section(app, container):
    section = _section(container, '01  选择设备')
    _add_summary_label(section, app.device_summary_var)
    table = ttk.Frame(section)
    table.pack(fill=tk.X)
    table.columnconfigure(0, weight=1)
    app.device_tree = ttk.Treeview(table, columns=('device_id','name','status','platform'),
        displaycolumns=DEVICE_DISPLAY_COLUMNS, show='headings', selectmode='extended', height=1)
    configure_device_tree(app.device_tree)
    app.device_tree.grid(row=0, column=0, sticky=tk.NSEW)
    app.device_tree.bind('<<TreeviewSelect>>', app.on_device_select)
    vertical = ttk.Scrollbar(table, command=app.device_tree.yview)
    vertical.grid(row=0, column=1, sticky=tk.NS)
    horizontal = ttk.Scrollbar(table, orient=tk.HORIZONTAL, command=app.device_tree.xview)
    horizontal.grid(row=1, column=0, sticky=tk.EW)
    app.device_tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    actions = ActionRow(section)
    actions.pack(fill=tk.X, pady=4)
    app.refresh_button = actions.add('刷新设备', app.refresh_devices_and_packages)
    app.udid_button = actions.add('获取UDID', app.fetch_hdc_udid)
    app.crash_log_button = actions.add('获取崩溃日志', app.fetch_crash_log)
    app.nextdemo_log_button = actions.add('获取NEXTdemo日志', app.fetch_nextdemo_log)
    _add_summary_label(section, app.device_action_hint_var)
    ttk.Label(section, text='自定义名称（单选设备）').pack(anchor=tk.W, pady=(6, 2))
    app.name_entry = ttk.Entry(section, textvariable=app.name_var, width=1)
    app.name_entry.pack(fill=tk.X)
    names = ActionRow(section)
    names.pack(fill=tk.X)
    names.add('保存名称', app.save_device_name)
    names.add('复制设备码', app.copy_selected_device_id)


def _build_package_section(app, container):
    section = _section(container, '02  选择安装包')
    ttk.Label(section, text='安装包目录').pack(anchor=tk.W)
    ttk.Entry(section, textvariable=app.folder_var, width=1).pack(fill=tk.X, pady=4)
    actions = ActionRow(section)
    actions.pack(fill=tk.X, pady=(0, 6))
    actions.add('选择目录', app.choose_folder)
    app.scan_button = actions.add('扫描最新包', app.refresh_devices_and_packages)
    for platform, variable, callback, attr in (
        ('APK · Android', app.apk_var, app.on_apk_selected, 'apk_combo'),
        ('HAP · Harmony', app.hap_var, app.on_hap_selected, 'hap_combo'),
    ):
        ttk.Label(section, text=platform).pack(anchor=tk.W)
        combo = ttk.Combobox(section, textvariable=variable, state='disabled', width=1,
            height=PACKAGE_COMBO_VISIBLE_ROWS)
        combo.pack(fill=tk.X, pady=(2, 6))
        combo.bind('<<ComboboxSelected>>', callback)
        setattr(app, attr, combo)
    ttk.Checkbutton(section, text='APK 需要 -t 安装', variable=app.apk_test_var).pack(anchor=tk.W)
    ttk.Button(section, text='保存此 APK 的 -t 设置', command=app.remember_apk_need_t).pack(anchor=tk.W, pady=4)


def _build_log_section(app, container):
    section = _section(container, '04  日志')
    actions = ActionRow(section)
    actions.pack(fill=tk.X)
    actions.add('复制日志', app.copy_log)
    actions.add('清空日志', app.clear_log)
    text_frame = ttk.Frame(section)
    text_frame.pack(fill=tk.BOTH, expand=True)
    text_frame.columnconfigure(0, weight=1)
    app.log_text = tk.Text(text_frame, height=10, width=1, wrap=tk.NONE, takefocus=True)
    app.log_text.grid(row=0, column=0, sticky=tk.NSEW)
    vertical = ttk.Scrollbar(text_frame, command=app.log_text.yview)
    vertical.grid(row=0, column=1, sticky=tk.NS)
    horizontal = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=app.log_text.xview)
    horizontal.grid(row=1, column=0, sticky=tk.EW)
    app.log_text.configure(state=tk.DISABLED, yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    app.log_text.bind('<Tab>', lambda event: _focus_next(event.widget))
    app.log_text.bind('<Shift-Tab>', lambda event: _focus_next(event.widget, reverse=True))
    _add_summary_label(container, text='Tab 切换操作 · Ctrl+Home/End 到页首/页尾 · Ctrl+PageUp/PageDown 翻页')


def _add_summary_label(parent, variable=None, *, text=None):
    label = ttk.Label(parent, textvariable=variable, text=text, wraplength=SUMMARY_WRAP_LENGTH)
    label.pack(fill=tk.X, pady=2)
    label.bind('<Configure>', lambda event: label.configure(wraplength=max(1, event.width-4)))
    return label


def _focus_next(widget, reverse=False):
    target = widget.tk_focusPrev() if reverse else widget.tk_focusNext()
    target.focus_set()
    return 'break'
