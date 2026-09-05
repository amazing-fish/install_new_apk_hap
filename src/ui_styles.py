"""Existing visual settings, retaining the platform's native ttk theme."""

import tkinter as tk
from tkinter import font as tkfont, ttk


WINDOW_TITLE = "APK/HAP 安装工具"
MIN_WINDOW_SIZE = (480, 560)
DEVICE_LIST_MIN_ROWS = 4
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


def configure_window(window: tk.Tk) -> None:
    window.title(WINDOW_TITLE)
    window.geometry(DEFAULT_GEOMETRY)
    window.minsize(*MIN_WINDOW_SIZE)
    style = ttk.Style(window)
    font = tkfont.nametofont('TkDefaultFont', root=window)
    style.configure('Section.TLabel', font=(font.actual('family'), font.actual('size'), 'bold'))
    style.configure('Hint.TLabel', foreground='#62666e')
    style.configure('Compact.TButton', padding=(6, 1), width=0)
    style.configure('Primary.TButton', padding=(14, 7))


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
    window.geometry(f'{max(MIN_WINDOW_SIZE[0], width)}x{DEFAULT_HEIGHT}')


def fit_device_columns(tree: ttk.Treeview) -> None:
    font = tkfont.Font(root=tree, font=ttk.Style(tree).lookup('Treeview', 'font') or 'TkDefaultFont')
    for column, title, minimum in DEVICE_COLUMN_STYLES:
        texts = [title, *(tree.set(item, column) for item in tree.get_children())]
        tree.column(column, width=max(minimum, max(font.measure(text) for text in texts) + 24))
