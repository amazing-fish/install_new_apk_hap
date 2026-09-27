"""Window, theme and visual constants.

The Sun Valley (sv-ttk) light theme is used when available; any failure to
load it falls back to the platform's native ttk theme so startup never fails.
"""

import os
import tkinter as tk
from tkinter import font as tkfont, ttk


WINDOW_TITLE = "APK/HAP 安装工具"
MIN_WINDOW_SIZE = (480, 560)
DEVICE_LIST_MIN_ROWS = 3
DEVICE_LIST_MAX_ROWS = 8
PACKAGE_COMBO_VISIBLE_ROWS = 10
SUMMARY_WRAP_LENGTH = 460
NEW_DEVICE_BACKGROUND = "#DFF6DD"
DEVICE_COLUMN_STYLES = (
    ("device_id", "设备码", 210),
    ("name", "名称", 140),
    ("status", "状态", 80),
    ("platform", "平台", 100),
)
DEFAULT_HEIGHT = 740
# Initial estimate; fit_initial_window measures actual native borders/scrollbars.
DEFAULT_GEOMETRY = f"{sum(width for _, _, width in DEVICE_COLUMN_STYLES) + 60}x{DEFAULT_HEIGHT}"

THEME_NAME = "sun-valley-light"
HINT_FOREGROUND = "#62666e"
BORDER_COLOR = "#d6d6d6"
ACCENT_COLOR = "#005fb8"
SELECTED_ROW_BACKGROUND = "#cfe3f7"
SELECTED_ROW_FOREGROUND = "#1c1c1c"
LOG_FONT_FAMILIES = ("Cascadia Mono", "Consolas")
# sv-ttk declares these in pixels (which do not follow `tk scaling` on high
# DPI) and in "Segoe UI Variable", which has no CJK glyphs, so Chinese text
# would fall back to a mismatched font. Keep sv-ttk's sizes scaled to the
# display, use the system UI family, and express Semibold as bold.
_SUN_VALLEY_FONTS = {
    "SunValleyCaptionFont": "normal", "SunValleyBodyFont": "normal",
    "SunValleyBodyStrongFont": "bold", "SunValleyBodyLargeFont": "normal",
    "SunValleySubtitleFont": "bold", "SunValleyTitleFont": "bold",
    "SunValleyTitleLargeFont": "bold", "SunValleyDisplayFont": "bold",
}


def enable_high_dpi() -> None:
    """Render natively at the display's scale instead of being bitmap-stretched.

    System-aware rather than per-monitor: Tk does not handle WM_DPICHANGED, so
    across monitors with different scales Windows keeps scaling the window.
    Must run before the first Tk window is created.
    """
    if os.name != "nt":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def ui_scale(window: tk.Misc) -> float:
    """Pixels per 96-DPI pixel (1.0 at 100%, 1.25 at 125%, ...)."""
    return max(1.0, float(window.tk.call("tk", "scaling")) * 72 / 96)


def apply_theme(window: tk.Tk) -> bool:
    """Use Sun Valley light when it loads; otherwise keep the native theme."""
    try:
        import sv_ttk
        sv_ttk.set_theme("light", window)
        # sv-ttk recolours widgets with tk_setPalette from a <<ThemeChanged>>
        # class binding. That event is re-queued by later style/font changes and
        # would overwrite every colour configured below once widgets exist, so
        # run the handler once now and drop the binding (the theme never changes
        # at runtime).
        root_class = window.winfo_class()
        window.tk.call("configure_colors")
        window.tk.call("bind", root_class, "<<ThemeChanged>>", "")
    except (ImportError, tk.TclError, RuntimeError, TypeError):
        return False
    # tk_setPalette also writes *foreground/*background into the option
    # database; ttk labels would take those as widget options and ignore
    # every style colour (e.g. the grey Hint.TLabel).
    window.option_add("*TLabel.foreground", "")
    window.option_add("*TLabel.background", "")
    scale = ui_scale(window)
    family = tkfont.nametofont("TkDefaultFont", root=window).actual("family")
    for name, weight in _SUN_VALLEY_FONTS.items():
        named = tkfont.nametofont(name, root=window)
        size = int(named.cget("size"))
        if size < 0:  # negative = pixels
            size = round(size * scale)
        named.configure(family=family, size=size, weight=weight)
    return True


def theme_active(window: tk.Misc) -> bool:
    return ttk.Style(window).theme_use() == THEME_NAME


def configure_window(window: tk.Tk) -> None:
    window.title(WINDOW_TITLE)
    themed = apply_theme(window)
    scale = ui_scale(window)
    width = round((sum(width for _, _, width in DEVICE_COLUMN_STYLES) + 60) * scale)
    window.geometry(f"{width}x{round(DEFAULT_HEIGHT * scale)}")
    window.minsize(*MIN_WINDOW_SIZE)
    style = ttk.Style(window)
    body = tkfont.nametofont("SunValleyBodyFont" if themed else "TkDefaultFont", root=window)
    strong = ("SunValleyBodyStrongFont" if themed
              else (body.actual("family"), body.actual("size"), "bold"))
    style.configure("Section.TLabel", font=strong)
    style.configure("Hint.TLabel", foreground=HINT_FOREGROUND)
    style.configure("Compact.TButton", padding=(8, 2) if themed else (6, 1), width=0)
    if themed:
        # The install action is the one primary button: give it the accent style.
        style.layout("Primary.TButton", style.layout("Accent.TButton"))
        style.configure("Primary.TButton", **style.configure("Accent.TButton"))
        style.map("Primary.TButton", **style.map("Accent.TButton"))
        style.configure("Primary.TButton", padding=(18, 6))
        style.map("Treeview",
                  background=[("selected", SELECTED_ROW_BACKGROUND)],
                  foreground=[("selected", SELECTED_ROW_FOREGROUND)])
        # Classic tk.Text (the log) has no ttk style: match the themed fields.
        window.option_add("*Text.relief", "flat")
        window.option_add("*Text.highlightThickness", 1)
        window.option_add("*Text.highlightBackground", BORDER_COLOR)
        window.option_add("*Text.highlightColor", ACCENT_COLOR)
        window.option_add("*Text.borderWidth", 0)
    else:
        style.configure("Primary.TButton", padding=(14, 7))
        window.option_add("*Text.relief", "solid")
        window.option_add("*Text.borderWidth", 1)
    available = set(tkfont.families(window))
    family = next((name for name in LOG_FONT_FAMILIES if name in available), None)
    if family:
        tkfont.nametofont("TkFixedFont", root=window).configure(family=family)


def configure_device_tree(tree: ttk.Treeview) -> None:
    for column, title, width in DEVICE_COLUMN_STYLES:
        tree.heading(column, text=title)
        tree.column(column, width=width, minwidth=width, stretch=False)
    tree.tag_configure("new_device", background=NEW_DEVICE_BACKGROUND)
    font = tkfont.Font(root=tree, font=ttk.Style(tree).lookup('Treeview', 'font') or 'TkDefaultFont')
    ttk.Style(tree).configure('Treeview', rowheight=max(20, font.metrics('linespace') + 4))


def fit_initial_window(window: tk.Tk, tree: ttk.Treeview) -> None:
    """Fit the four baseline columns once; later refreshes never resize the window."""
    window.update_idletasks()
    width = window.winfo_width() + tree.winfo_reqwidth() - tree.winfo_width()
    height = round(DEFAULT_HEIGHT * ui_scale(window))
    window.geometry(f'{max(MIN_WINDOW_SIZE[0], width)}x{height}')


def fit_device_columns(tree: ttk.Treeview) -> None:
    font = tkfont.Font(root=tree, font=ttk.Style(tree).lookup('Treeview', 'font') or 'TkDefaultFont')
    for column, title, minimum in DEVICE_COLUMN_STYLES:
        texts = [title, *(tree.set(item, column) for item in tree.get_children())]
        tree.column(column, width=max(minimum, max(font.measure(text) for text in texts) + 24))
