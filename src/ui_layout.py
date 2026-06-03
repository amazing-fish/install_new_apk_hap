import tkinter as tk
from tkinter import ttk

from ui_styles import SUCCESS_BG, WINDOW_BG, configure_styles


def _compact_button(parent, text: str, command):
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg="#FAFBFC",
        fg="#263241",
        activebackground="#EEF2F4",
        activeforeground="#263241",
        relief=tk.SOLID,
        borderwidth=1,
        padx=8,
        pady=1,
        cursor="hand2",
    )


def build_main_layout(app) -> None:
    configure_styles(app)
    app.columnconfigure(0, weight=1)
    app.rowconfigure(0, weight=1)

    scroll_host = ttk.Frame(app)
    scroll_host.grid(row=0, column=0, sticky="nsew")
    scroll_host.columnconfigure(0, weight=1)
    scroll_host.rowconfigure(0, weight=1)

    app.main_canvas = tk.Canvas(
        scroll_host,
        bg=WINDOW_BG,
        borderwidth=0,
        highlightthickness=0,
    )
    app.main_canvas.grid(row=0, column=0, sticky="nsew")
    app.main_scrollbar = ttk.Scrollbar(
        scroll_host,
        orient=tk.VERTICAL,
        command=app.main_canvas.yview,
    )
    app.main_scrollbar.grid(row=0, column=1, sticky="ns")
    app.main_canvas.configure(yscrollcommand=_main_scrollbar_setter(app))

    container = ttk.Frame(app.main_canvas, padding=(10, 8))
    app.main_content_frame = container
    app.main_canvas_window = app.main_canvas.create_window(
        (0, 0),
        window=container,
        anchor="nw",
    )
    container.columnconfigure(0, weight=1)
    container.rowconfigure(1, weight=0)
    container.rowconfigure(2, weight=0)
    container.rowconfigure(4, weight=1, minsize=96)

    container.bind("<Configure>", lambda _event: _sync_main_scroll_region(app))
    app.main_canvas.bind("<Configure>", lambda event: _sync_main_canvas_width(app, event.width))

    _build_header(app, container)
    _build_device_section(app, container)
    _build_package_section(app, container)
    _build_execution(app, container)
    _build_log(app, container)
    _bind_main_mousewheel(container, app.main_canvas)


def _main_scrollbar_setter(app):
    def update_scrollbar(first: str, last: str) -> None:
        first_value = float(first)
        last_value = float(last)
        if first_value <= 0.0 and last_value >= 1.0:
            app.main_scrollbar.grid_remove()
        else:
            app.main_scrollbar.grid(row=0, column=1, sticky="ns")
        app.main_scrollbar.set(first, last)

    return update_scrollbar


def _sync_main_scroll_region(app) -> None:
    app.main_canvas.configure(scrollregion=app.main_canvas.bbox("all"))


def _sync_main_canvas_width(app, width: int) -> None:
    app.main_canvas.itemconfigure(app.main_canvas_window, width=width)


def _bind_main_mousewheel(widget, canvas: tk.Canvas) -> None:
    widgets_with_own_scroll = (tk.Text, ttk.Combobox, ttk.Treeview)

    def on_mousewheel(event: tk.Event) -> str | None:
        first, last = canvas.yview()
        if first <= 0.0 and last >= 1.0:
            return None
        if event.delta:
            canvas.yview_scroll(int(-event.delta / 120), "units")
        elif getattr(event, "num", None) == 4:
            canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            canvas.yview_scroll(1, "units")
        return "break"

    if isinstance(widget, widgets_with_own_scroll):
        return

    widget.bind("<MouseWheel>", on_mousewheel, add="+")
    widget.bind("<Button-4>", on_mousewheel, add="+")
    widget.bind("<Button-5>", on_mousewheel, add="+")
    for child in widget.winfo_children():
        _bind_main_mousewheel(child, canvas)


def _build_header(app, parent: ttk.Frame) -> None:
    header = ttk.Frame(parent)
    header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
    header.columnconfigure(0, weight=1)

    ttk.Label(header, text="APK/HAP 安装控制台", style="Title.TLabel").grid(
        row=0,
        column=0,
        sticky="w",
    )
    ttk.Label(header, textvariable=app.install_status_var, style="Muted.TLabel").grid(
        row=0,
        column=1,
        sticky="e",
    )


def _build_device_section(app, parent: ttk.Frame) -> None:
    device_frame = ttk.LabelFrame(parent, text="设备", style="Section.TLabelframe", padding=(10, 8))
    device_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    device_frame.columnconfigure(0, weight=1)

    top_row = ttk.Frame(device_frame, style="Surface.TFrame")
    top_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
    top_row.columnconfigure(0, weight=1)
    ttk.Label(top_row, textvariable=app.device_summary_var, style="SurfaceMuted.TLabel").grid(
        row=0,
        column=0,
        sticky="w",
    )
    app.refresh_button = ttk.Button(top_row, text="刷新设备", command=app.refresh_devices)
    app.refresh_button.grid(row=0, column=1, sticky="e")

    tree_wrap = ttk.Frame(device_frame, style="Surface.TFrame")
    tree_wrap.grid(row=1, column=0, sticky="ew")
    tree_wrap.columnconfigure(0, weight=1)

    columns = ("name", "platform", "status", "device_id")
    app.device_tree = ttk.Treeview(
        tree_wrap,
        columns=columns,
        show="headings",
        selectmode="extended",
        height=1,
    )
    app.device_tree.heading("name", text="名称")
    app.device_tree.heading("platform", text="平台")
    app.device_tree.heading("status", text="状态")
    app.device_tree.heading("device_id", text="设备码")
    app.device_tree.column("name", width=86, minwidth=60, stretch=False)
    app.device_tree.column("platform", width=64, minwidth=56, stretch=False)
    app.device_tree.column("status", width=70, minwidth=64, stretch=False)
    app.device_tree.column("device_id", width=210, minwidth=150, stretch=True)
    app.device_tree.tag_configure("new_device", background=SUCCESS_BG)
    app.device_tree.grid(row=0, column=0, sticky="ew")
    app.device_tree.bind("<<TreeviewSelect>>", app.on_device_select)

    y_scrollbar = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=app.device_tree.yview)
    x_scrollbar = ttk.Scrollbar(tree_wrap, orient=tk.HORIZONTAL, command=app.device_tree.xview)
    _attach_auto_scrollbar(app.device_tree, y_scrollbar, "yscrollcommand", row=0, column=1, sticky="ns")
    _attach_auto_scrollbar(app.device_tree, x_scrollbar, "xscrollcommand", row=1, column=0, sticky="ew")

    _build_device_name_row(app, device_frame)


def _build_device_name_row(app, parent: ttk.LabelFrame) -> None:
    name_row = ttk.Frame(parent, style="Surface.TFrame")
    name_row.grid(row=2, column=0, sticky="ew", pady=(6, 0))
    name_row.columnconfigure(1, weight=0)

    ttk.Label(name_row, text="名称", style="Surface.TLabel").grid(
        row=0,
        column=0,
        sticky="w",
        padx=(0, 8),
    )
    app.name_var = tk.StringVar()
    app.name_entry = ttk.Entry(name_row, textvariable=app.name_var, width=18)
    app.name_entry.grid(row=0, column=1, sticky="w", padx=(0, 6))
    app.save_name_button = _compact_button(name_row, "保存", app.save_device_name)
    app.save_name_button.grid(row=0, column=2, sticky="e")

    command_row = ttk.Frame(parent, style="Surface.TFrame")
    command_row.grid(row=3, column=0, sticky="w", pady=(6, 0))
    for index, (text, command, role) in enumerate(
        (
            ("设备码", app.copy_selected_device_id, "copy"),
            ("UDID", app.fetch_hdc_udid, "udid"),
            ("崩溃日志", app.fetch_crash_log, "crash"),
            ("NEXTdemo", app.fetch_nextdemo_log, "nextdemo"),
        )
    ):
        button = _compact_button(command_row, text, command)
        row = index // 2
        column = index % 2
        button.grid(
            row=row,
            column=column,
            sticky="w",
            padx=(0, 8),
            pady=(0, 5),
        )
        if role == "copy":
            app.copy_device_button = button
        if role == "udid":
            app.udid_button = button
        elif role == "crash":
            app.crash_log_button = button
        elif role == "nextdemo":
            app.nextdemo_log_button = button


def _build_package_section(app, parent: ttk.Frame) -> None:
    package_frame = ttk.LabelFrame(parent, text="安装包", style="Section.TLabelframe", padding=(10, 8))
    package_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    package_frame.columnconfigure(0, weight=1)

    folder_row = ttk.Frame(package_frame, style="Surface.TFrame")
    folder_row.grid(row=0, column=0, sticky="ew", pady=(0, 5))
    folder_row.columnconfigure(0, weight=1)
    app.folder_var = tk.StringVar()
    ttk.Entry(folder_row, textvariable=app.folder_var).grid(row=0, column=0, sticky="ew")

    folder_buttons = ttk.Frame(package_frame, style="Surface.TFrame")
    folder_buttons.grid(row=1, column=0, sticky="w", pady=(0, 6))
    ttk.Button(folder_buttons, text="选择目录", command=app.choose_folder).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(folder_buttons, text="扫描", command=app.scan_latest_packages).grid(row=0, column=1)

    app.apk_var = tk.StringVar(value="未找到")
    app.apk_display_entry = _build_package_picker(
        package_frame,
        row=2,
        label="APK",
        variable=app.apk_var,
        bind_callback=app.on_apk_selected,
        assign=lambda combo: setattr(app, "apk_combo", combo),
    )

    app.hap_var = tk.StringVar(value="未找到")
    app.hap_display_entry = _build_package_picker(
        package_frame,
        row=3,
        label="HAP",
        variable=app.hap_var,
        bind_callback=app.on_hap_selected,
        assign=lambda combo: setattr(app, "hap_combo", combo),
    )

    app.apk_test_var = tk.BooleanVar(value=False)
    option_row = ttk.Frame(package_frame, style="Surface.TFrame")
    option_row.grid(row=4, column=0, sticky="w", pady=(4, 0))
    ttk.Checkbutton(
        option_row,
        text="APK 需要 -t 安装",
        variable=app.apk_test_var,
    ).grid(row=0, column=0, sticky="w", padx=(0, 8))
    ttk.Button(
        option_row,
        text="记住 -t",
        command=app.remember_apk_need_t,
    ).grid(row=0, column=1, sticky="w")


def _build_package_picker(
    parent: ttk.LabelFrame,
    row: int,
    label: str,
    variable: tk.StringVar,
    bind_callback,
    assign,
) -> ttk.Entry:
    picker = ttk.Frame(parent, style="Surface.TFrame")
    picker.grid(row=row, column=0, sticky="ew", pady=(0, 5))
    picker.columnconfigure(1, weight=1)

    ttk.Label(picker, text=label, style="Surface.TLabel", width=4).grid(
        row=0,
        column=0,
        sticky="w",
        padx=(0, 6),
    )
    display_entry = ttk.Entry(picker, textvariable=variable, state="readonly", width=12)
    display_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))

    combo = ttk.Combobox(picker, textvariable=variable, state="disabled", width=24)
    combo.grid(row=1, column=1, sticky="ew", pady=(3, 0))
    combo.bind("<<ComboboxSelected>>", bind_callback)
    assign(combo)

    x_scrollbar = ttk.Scrollbar(picker, orient=tk.HORIZONTAL, command=display_entry.xview)
    _attach_auto_scrollbar(display_entry, x_scrollbar, "xscrollcommand", row=2, column=1, sticky="ew")
    return display_entry


def _build_execution(app, parent: ttk.Frame) -> None:
    execution = ttk.LabelFrame(parent, text="执行", style="Section.TLabelframe", padding=(10, 8))
    execution.grid(row=3, column=0, sticky="ew", pady=(0, 8))
    execution.columnconfigure(1, weight=1)

    app.install_button = tk.Button(
        execution,
        text="安装到所选设备",
        command=app.install_to_selected,
        bg="#256F7F",
        fg="#FFFFFF",
        activebackground="#1D5A68",
        activeforeground="#FFFFFF",
        relief=tk.FLAT,
        padx=12,
        pady=5,
        cursor="hand2",
    )
    app.install_button.grid(row=0, column=0, sticky="w", padx=(0, 12))

    summary_group = ttk.Frame(execution, style="Surface.TFrame")
    summary_group.grid(row=0, column=1, sticky="ew")
    summary_group.columnconfigure(0, weight=1)
    ttk.Label(summary_group, textvariable=app.selected_device_var, style="Surface.TLabel").grid(
        row=0,
        column=0,
        sticky="w",
    )
    ttk.Label(summary_group, textvariable=app.install_status_var, style="SurfaceMuted.TLabel").grid(
        row=1,
        column=0,
        sticky="w",
    )


def _build_log(app, parent: ttk.Frame) -> None:
    log_frame = ttk.LabelFrame(parent, text="日志", style="Section.TLabelframe", padding=(10, 8))
    log_frame.grid(row=4, column=0, sticky="nsew")
    log_frame.columnconfigure(0, weight=1)
    log_frame.rowconfigure(1, weight=1)

    log_buttons = ttk.Frame(log_frame, style="Surface.TFrame")
    log_buttons.grid(row=0, column=0, sticky="ew", pady=(0, 5))
    ttk.Button(log_buttons, text="复制日志", command=app.copy_log).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(log_buttons, text="清空", command=app.clear_log).grid(row=0, column=1)

    text_wrap = ttk.Frame(log_frame, style="Surface.TFrame")
    text_wrap.grid(row=1, column=0, sticky="nsew")
    text_wrap.columnconfigure(0, weight=1)
    text_wrap.rowconfigure(0, weight=1)

    app.log_text = tk.Text(
        text_wrap,
        height=7,
        wrap=tk.NONE,
        borderwidth=1,
        relief=tk.SOLID,
        padx=8,
        pady=6,
        bg="#FBFCFD",
        fg="#253241",
        insertbackground="#253241",
        selectbackground="#DCEAF0",
        font=("Consolas", 9),
    )
    app.log_text.grid(row=0, column=0, sticky="nsew")
    app.log_text.configure(state=tk.DISABLED)

    y_scrollbar = ttk.Scrollbar(text_wrap, orient=tk.VERTICAL, command=app.log_text.yview)
    x_scrollbar = ttk.Scrollbar(text_wrap, orient=tk.HORIZONTAL, command=app.log_text.xview)
    _attach_auto_scrollbar(app.log_text, y_scrollbar, "yscrollcommand", row=0, column=1, sticky="ns")
    _attach_auto_scrollbar(app.log_text, x_scrollbar, "xscrollcommand", row=1, column=0, sticky="ew")


def _attach_auto_scrollbar(widget, scrollbar: ttk.Scrollbar, scroll_option: str, **grid_options) -> None:
    def update_scrollbar(first: str, last: str) -> None:
        first_value = float(first)
        last_value = float(last)
        if first_value <= 0.0 and last_value >= 1.0:
            scrollbar.grid_remove()
        else:
            scrollbar.grid(**grid_options)
        scrollbar.set(first, last)

    widget.configure(**{scroll_option: update_scrollbar})
    scrollbar.grid(**grid_options)
    scrollbar.grid_remove()
