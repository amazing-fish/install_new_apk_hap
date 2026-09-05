"""One-time UI assembly using App-owned variables and callbacks."""

import tkinter as tk
from tkinter import font as tkfont, ttk
from typing import TYPE_CHECKING

from ui_display import DEVICE_DISPLAY_COLUMNS
from ui_styles import DEVICE_LIST_MIN_ROWS, PACKAGE_COMBO_VISIBLE_ROWS, SUMMARY_WRAP_LENGTH, configure_device_tree
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
    _build_log_section(app, container)


def _section(parent, title):
    frame = ttk.Frame(parent)
    frame.pack(fill=tk.X, pady=(2, 6))
    heading = ttk.Frame(frame)
    heading.pack(fill=tk.X, pady=(0, 5))
    ttk.Label(heading, text=title, style='Section.TLabel').pack(side=tk.LEFT, padx=(0, 12))
    return frame, heading


def _build_execution_bar(app):
    bar = ttk.Frame(app, padding=(12, 8))
    bar.pack(side=tk.BOTTOM, fill=tk.X)
    bar.columnconfigure(0, weight=1)
    # Compact mirror; the full, wrapping summary is in the scrollable section.
    app.status_selection_label = ttk.Label(bar, textvariable=app.selected_device_summary_var, width=1)
    app.status_selection_label.grid(row=0, column=0, sticky=tk.EW, padx=(0, 8))
    app.install_button = ttk.Button(bar, text='安装到所选设备', command=app.install_to_selected,
        style='Primary.TButton', default=tk.ACTIVE)
    app.install_button.grid(row=0, column=1, rowspan=2, sticky=tk.E)
    ttk.Label(bar, textvariable=app.install_status_var, style='Hint.TLabel').grid(row=1, column=0, sticky=tk.W)
    ttk.Separator(app).pack(side=tk.BOTTOM, fill=tk.X)


def _build_device_section(app, container):
    section, heading = _section(container, '设备')
    summary = _add_summary_label(heading, app.device_summary_var)
    summary.pack_configure(side=tk.LEFT, expand=True)
    table = ttk.Frame(section)
    table.pack(fill=tk.X)
    table.columnconfigure(0, weight=1)
    app.device_tree = ttk.Treeview(table, columns=('device_id','name','status','platform'),
        displaycolumns=DEVICE_DISPLAY_COLUMNS, show='headings', selectmode='extended', height=DEVICE_LIST_MIN_ROWS)
    configure_device_tree(app.device_tree)
    app.device_tree.grid(row=0, column=0, sticky=tk.NSEW)
    app.device_tree.bind('<<TreeviewSelect>>', app.on_device_select)
    vertical = ttk.Scrollbar(table, command=app.device_tree.yview)
    vertical.grid(row=0, column=1, sticky=tk.NS)
    horizontal = ttk.Scrollbar(table, orient=tk.HORIZONTAL, command=app.device_tree.xview)
    horizontal.grid(row=1, column=0, sticky=tk.EW)
    app.device_tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    actions = ActionRow(section)
    actions.pack(fill=tk.X, pady=(3, 0))
    app.refresh_button = actions.add('刷新设备', app.refresh_devices_and_packages)
    app.udid_button = actions.add('获取UDID', app.fetch_hdc_udid)
    app.crash_log_button = actions.add('获取崩溃日志', app.fetch_crash_log)
    app.nextdemo_log_button = actions.add('获取NEXTdemo日志', app.fetch_nextdemo_log)
    app.name_entry = _field_row(section, '名称', app.name_var, actions=(
        ('保存名称', app.save_device_name), ('复制设备码', app.copy_selected_device_id)))
    app.execution_selection_label = _add_summary_label(section, app.selected_device_summary_var)
    _show_clipped_summary(app.execution_selection_label,
        [(app.status_selection_label, app.selected_device_summary_var)])


def _build_package_section(app, container):
    section, _heading = _section(container, '安装包')
    folder = _field_row(section, '目录', app.folder_var, actions=(
        ('选择目录', app.choose_folder), ('扫描最新包', app.refresh_devices_and_packages)))
    app.scan_button = folder.actions.buttons[1]
    for platform, variable, callback, attr in (
        ('APK', app.apk_var, app.on_apk_selected, 'apk_combo'),
        ('HAP', app.hap_var, app.on_hap_selected, 'hap_combo'),
    ):
        combo = _field_row(section, platform, variable, combo=True)
        combo.bind('<<ComboboxSelected>>', callback)
        setattr(app, attr, combo)
    options = ActionRow(section)
    options.pack(fill=tk.X, pady=(2, 0))
    options.add_widget(ttk.Checkbutton(options, text='APK 需要 -t 安装', variable=app.apk_test_var))
    options.add('保存此 APK 的 -t 设置', app.remember_apk_need_t)
    summary = _add_summary_label(section, app.package_summary_var)
    _show_clipped_summary(summary, [(app.apk_combo, app.apk_var), (app.hap_combo, app.hap_var)])


def _build_log_section(app, container):
    section, heading = _section(container, '日志')
    actions = ActionRow(heading)
    actions.pack(side=tk.RIGHT, fill=tk.X, expand=True)
    actions.add('复制日志', app.copy_log)
    actions.add('清空日志', app.clear_log)
    text_frame = ttk.Frame(section)
    text_frame.pack(fill=tk.BOTH, expand=True)
    text_frame.columnconfigure(0, weight=1)
    app.log_text = tk.Text(text_frame, height=6, width=1, wrap=tk.NONE, takefocus=True,
        relief=tk.SOLID, borderwidth=1, padx=6, pady=4, font='TkFixedFont')
    app.log_text.grid(row=0, column=0, sticky=tk.NSEW)
    vertical = ttk.Scrollbar(text_frame, command=app.log_text.yview)
    vertical.grid(row=0, column=1, sticky=tk.NS)
    horizontal = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=app.log_text.xview)
    horizontal.grid(row=1, column=0, sticky=tk.EW)
    app.log_text.configure(state=tk.DISABLED, yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    app.log_text.bind('<Tab>', lambda event: _focus_next(event.widget))
    app.log_text.bind('<Shift-Tab>', lambda event: _focus_next(event.widget, reverse=True))


def _field_row(parent, title, variable, *, actions=(), combo=False):
    """Keep short fields and their actions together, wrapping actions if needed."""
    row = ttk.Frame(parent)
    row.pack(fill=tk.X, pady=2)
    row.columnconfigure(1, weight=1)
    label = ttk.Label(row, text=title, width=5)
    label.grid(row=0, column=0, sticky=tk.W, padx=(0, 6))
    if combo:
        field = ttk.Combobox(row, textvariable=variable, state='disabled', width=1,
            height=PACKAGE_COMBO_VISIBLE_ROWS)
    else:
        field = ttk.Entry(row, textvariable=variable, width=1)
    field.grid(row=0, column=1, sticky=tk.EW)
    if actions:
        buttons = field.actions = ActionRow(row)
        for text, command in actions:
            buttons.add(text, command)
        buttons.grid(row=0, column=2, sticky=tk.EW, padx=(6, 0))

        def arrange(event):
            font = tkfont.nametofont('TkDefaultFont', root=row)
            action_width = buttons.natural_width()
            inline = event.width >= label.winfo_reqwidth() + font.measure('0' * 12) + action_width + 12
            row.columnconfigure(2, minsize=action_width + 6 if inline else 0)
            buttons.grid(row=0 if inline else 1, column=2 if inline else 1,
                padx=(6, 0) if inline else 0)

        row.bind('<Configure>', arrange)
    return field


def _add_summary_label(parent, variable=None, *, text=None):
    label = ttk.Label(parent, textvariable=variable, text=text, wraplength=SUMMARY_WRAP_LENGTH,
        style='Hint.TLabel', width=1)
    label.pack(fill=tk.X, pady=1)
    label.bind('<Configure>', lambda event: label.configure(wraplength=max(1, event.width-4)))
    return label


def _show_clipped_summary(label, sources):
    """Only repeat full names when their primary control cannot show them."""
    def refresh(*_args):
        clipped = False
        for widget, variable in sources:
            font = tkfont.Font(root=widget, font=widget.cget('font') or 'TkDefaultFont')
            inset = 32 if isinstance(widget, ttk.Combobox) else 4
            clipped |= font.measure(variable.get()) > max(1, widget.winfo_width() - inset)
        if clipped:
            label.pack(fill=tk.X, pady=1)
        else:
            label.pack_forget()

    traces = []
    bindings = []
    for widget, variable in sources:
        bindings.append((widget, widget.bind('<Configure>', refresh, add='+')))
        traces.append((variable, variable.trace_add('write', refresh)))

    def cleanup(_event):
        for variable, trace in traces:
            variable.trace_remove('write', trace)
        for widget, binding in bindings:
            if widget.winfo_exists():
                widget.unbind('<Configure>', binding)

    label.bind('<Destroy>', cleanup)


def _focus_next(widget, reverse=False):
    target = widget.tk_focusPrev() if reverse else widget.tk_focusNext()
    target.focus_set()
    return 'break'
