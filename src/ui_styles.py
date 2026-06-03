from tkinter import ttk


WINDOW_BG = "#F6F7F8"
SURFACE = "#FFFFFF"
SURFACE_MUTED = "#E6EAEE"
TEXT_PRIMARY = "#18212F"
TEXT_SECONDARY = "#5C6878"
ACCENT = "#256F7F"
ACCENT_DARK = "#1D5A68"
DANGER = "#B42318"
SUCCESS_BG = "#DFF6DD"


def configure_styles(root) -> None:
    root.configure(bg=WINDOW_BG)
    style = ttk.Style(root)
    for theme_name in ("vista", "xpnative", "clam"):
        try:
            style.theme_use(theme_name)
            break
        except Exception:
            continue

    style.configure(".", font=("Segoe UI", 9), background=WINDOW_BG, foreground=TEXT_PRIMARY)
    style.configure("TFrame", background=WINDOW_BG)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("TLabel", background=WINDOW_BG, foreground=TEXT_PRIMARY)
    style.configure("Muted.TLabel", background=WINDOW_BG, foreground=TEXT_SECONDARY)
    style.configure("Surface.TLabel", background=SURFACE, foreground=TEXT_PRIMARY)
    style.configure("SurfaceMuted.TLabel", background=SURFACE, foreground=TEXT_SECONDARY)
    style.configure(
        "Title.TLabel",
        background=WINDOW_BG,
        foreground=TEXT_PRIMARY,
        font=("Segoe UI Semibold", 13),
    )
    style.configure(
        "Section.TLabelframe",
        background=SURFACE,
        bordercolor=SURFACE_MUTED,
        relief="solid",
    )
    style.configure(
        "Section.TLabelframe.Label",
        background=SURFACE,
        foreground=TEXT_PRIMARY,
        font=("Segoe UI Semibold", 10),
    )
    style.configure("TButton", padding=(5, 2))
    style.configure(
        "Accent.TButton",
        padding=(8, 3),
        background=ACCENT,
        foreground="#FFFFFF",
        bordercolor=ACCENT,
    )
    style.map(
        "Accent.TButton",
        background=[("active", ACCENT_DARK), ("disabled", SURFACE_MUTED)],
        foreground=[("disabled", TEXT_SECONDARY)],
    )
    style.configure(
        "Danger.TButton",
        padding=(8, 3),
        background=DANGER,
        foreground="#FFFFFF",
        bordercolor=DANGER,
    )
    style.configure("TEntry", padding=(5, 3))
    style.configure("TCombobox", padding=(5, 3))
    style.configure(
        "Treeview",
        background="#FFFFFF",
        fieldbackground="#FFFFFF",
        foreground=TEXT_PRIMARY,
        rowheight=24,
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        background=SURFACE_MUTED,
        foreground=TEXT_PRIMARY,
        font=("Segoe UI Semibold", 9),
        padding=(5, 4),
    )
    style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#FFFFFF")])
    style.configure("Horizontal.TScrollbar", arrowsize=11)
    style.configure("Vertical.TScrollbar", arrowsize=11)
