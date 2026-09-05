"""Existing visual settings, retaining the platform's native ttk theme."""

import tkinter as tk
from tkinter import font as tkfont, ttk


WINDOW_TITLE = "APK/HAP 安装工具"
DEFAULT_GEOMETRY = "720x780"
MIN_WINDOW_SIZE = (480, 560)
DEVICE_LIST_MAX_ROWS = 8
PACKAGE_COMBO_VISIBLE_ROWS = 10
SUMMARY_WRAP_LENGTH = 460
NEW_DEVICE_BACKGROUND = "#DFF6DD"
DEVICE_COLUMN_STYLES = (
    ("device_id", "设备码", 130),
    ("name", "名称", 100),
    ("status", "状态", 120),
    ("platform", "平台", 120),
)


def configure_window(window: tk.Tk) -> None:
    window.title(WINDOW_TITLE)
    window.geometry(DEFAULT_GEOMETRY)
    window.minsize(*MIN_WINDOW_SIZE)


def configure_device_tree(tree: ttk.Treeview) -> None:
    for column, title, width in DEVICE_COLUMN_STYLES:
        tree.heading(column, text=title)
        tree.column(column, width=width, minwidth=width, stretch=False)
    tree.tag_configure("new_device", background=NEW_DEVICE_BACKGROUND)


def fit_device_columns(tree: ttk.Treeview) -> None:
    font = tkfont.Font(root=tree, font=ttk.Style(tree).lookup('Treeview', 'font') or 'TkDefaultFont')
    for column, title, minimum in DEVICE_COLUMN_STYLES:
        texts = [title, *(tree.set(item, column) for item in tree.get_children())]
        tree.column(column, width=max(minimum, max(font.measure(text) for text in texts) + 24))
