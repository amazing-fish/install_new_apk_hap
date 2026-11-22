"""Windows native borderless-chrome, theme, DPI work-area sizing, and window controls."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import functools
import importlib.metadata
import os
from pathlib import Path
from typing import Optional, Tuple

if os.name == "nt":
    import winreg


DEFAULT_WINDOW_WIDTH = 860
DEFAULT_WINDOW_HEIGHT = 860
MIN_WINDOW_WIDTH = 700
MIN_WINDOW_HEIGHT = 660

_SPI_GETWORKAREA = 0x0030
_GWLP_WNDPROC = -4
_WM_NCDESTROY = 0x0082
_WM_NCCALCSIZE = 0x0083
_WM_NCLBUTTONDOWN = 0x00A1
_HTCAPTION = 2
_HTLEFT = 10
_HTRIGHT = 11
_HTTOP = 12
_HTTOPLEFT = 13
_HTTOPRIGHT = 14
_HTBOTTOM = 15
_HTBOTTOMLEFT = 16
_HTBOTTOMRIGHT = 17

_RESIZE_HIT_MAP = {
    "left": _HTLEFT,
    "right": _HTRIGHT,
    "top": _HTTOP,
    "top-left": _HTTOPLEFT,
    "top-right": _HTTOPRIGHT,
    "bottom": _HTBOTTOM,
    "bottom-left": _HTBOTTOMLEFT,
    "bottom-right": _HTBOTTOMRIGHT,
}

_SM_CXFRAME = 32
_SM_CYFRAME = 33
_SM_CXPADDEDBORDER = 92

_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2


def system_prefers_dark() -> bool:
    """Read Windows AppsUseLightTheme without importing .NET/WinForms."""
    if os.name != "nt":
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
    except OSError:
        return False


def resolve_theme_dark(theme: str) -> bool:
    if theme == "dark":
        return True
    if theme == "light":
        return False
    return system_prefers_dark()


def theme_background_color(theme: str) -> str:
    return "#0b0e14" if resolve_theme_dark(theme) else "#f3f5f8"


@functools.lru_cache(maxsize=1)
def _pywebview_major_version() -> int:
    try:
        return int(importlib.metadata.version("pywebview").split(".", 1)[0])
    except Exception:
        return 6


def enable_dpi_awareness() -> None:
    """Enable Windows process DPI awareness before querying primary work area."""
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except OSError:
        pass


def get_primary_work_area_logical() -> Optional[Tuple[int, int]]:
    """Return primary monitor working area (width, height) in logical pixels."""
    if os.name != "nt":
        return None
    try:
        rect = wintypes.RECT()
        ok = ctypes.windll.user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        if not ok:
            return None
        phys_w = max(0, rect.right - rect.left)
        phys_h = max(0, rect.bottom - rect.top)
        try:
            dpi = int(ctypes.windll.user32.GetDpiForSystem())
        except Exception:
            dpi = 96
        scale = max(1.0, (dpi or 96) / 96.0)
        return max(320, int(phys_w / scale)), max(240, int(phys_h / scale))
    except (OSError, AttributeError, ValueError):
        return None


def compute_initial_window_size(
    saved_width: Optional[int],
    saved_height: Optional[int],
    *,
    default_width: int = DEFAULT_WINDOW_WIDTH,
    default_height: int = DEFAULT_WINDOW_HEIGHT,
    min_width: int = MIN_WINDOW_WIDTH,
    min_height: int = MIN_WINDOW_HEIGHT,
    work_area: Optional[Tuple[int, int]] = None,
) -> Tuple[int, int, Tuple[int, int]]:
    """Resolve initial window width/height and clamped min_size for the active screen."""
    width = saved_width if isinstance(saved_width, int) and saved_width >= min_width else default_width
    height = saved_height if isinstance(saved_height, int) and saved_height >= min_height else default_height

    area = work_area if work_area is not None else get_primary_work_area_logical()
    if area is not None:
        avail_w, avail_h = area
        max_w = max(560, avail_w - 40)
        max_h = max(500, avail_h - 40)
        width = min(width, max_w)
        height = min(height, max_h)

    eff_min_w = min(min_width, width)
    eff_min_h = min(min_height, height)
    width = max(width, eff_min_w)
    height = max(height, eff_min_h)
    return int(width), int(height), (int(eff_min_w), int(eff_min_h))


if os.name == "nt":
    _user32 = ctypes.windll.user32
    _dwmapi = ctypes.windll.dwmapi

    _LONG_PTR = ctypes.c_ssize_t
    _UINT_PTR = ctypes.c_size_t
    _WNDPROC = ctypes.WINFUNCTYPE(_LONG_PTR, wintypes.HWND, wintypes.UINT, _UINT_PTR, _LONG_PTR)

    class _NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

    class _MARGINS(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth", ctypes.c_int),
            ("cxRightWidth", ctypes.c_int),
            ("cyTopHeight", ctypes.c_int),
            ("cyBottomHeight", ctypes.c_int),
        ]

    if ctypes.sizeof(ctypes.c_void_p) == 8:
        _SetWindowLongPtr = _user32.SetWindowLongPtrW
    else:
        _SetWindowLongPtr = _user32.SetWindowLongW
    _SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, _WNDPROC]
    _SetWindowLongPtr.restype = _LONG_PTR

    _CallWindowProc = _user32.CallWindowProcW
    _CallWindowProc.argtypes = [_LONG_PTR, wintypes.HWND, wintypes.UINT, _UINT_PTR, _LONG_PTR]
    _CallWindowProc.restype = _LONG_PTR

    _DefWindowProc = _user32.DefWindowProcW
    _DefWindowProc.argtypes = [wintypes.HWND, wintypes.UINT, _UINT_PTR, _LONG_PTR]
    _DefWindowProc.restype = _LONG_PTR

    _GetDpiForWindow = getattr(_user32, "GetDpiForWindow", None)
    if _GetDpiForWindow is not None:
        _GetDpiForWindow.argtypes = [wintypes.HWND]
        _GetDpiForWindow.restype = wintypes.UINT

    _GetSystemMetricsForDpi = getattr(_user32, "GetSystemMetricsForDpi", None)
    if _GetSystemMetricsForDpi is not None:
        _GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
        _GetSystemMetricsForDpi.restype = ctypes.c_int

    _IsZoomed = _user32.IsZoomed
    _IsZoomed.argtypes = [wintypes.HWND]
    _IsZoomed.restype = wintypes.BOOL

    _SendMessageW = _user32.SendMessageW
    _SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, _UINT_PTR, _LONG_PTR]
    _SendMessageW.restype = _LONG_PTR

    _SetWindowPos = _user32.SetWindowPos
    _SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    _SetWindowPos.restype = wintypes.BOOL


class NativeWindowController:
    """Manages Win32 borderless frame (WM_NCCALCSIZE), icon, theme, and window actions."""

    def __init__(self) -> None:
        self._form = None
        self._hwnd: int = 0
        self._old_wndproc: int = 0
        self._wndproc_ref = None
        self._attached = False

    def attach(self, window, icon_path: Optional[Path], theme: str) -> None:
        if os.name != "nt" or self._attached:
            return
        form = getattr(window, "native", None)
        if form is None:
            return
        self._form = form
        try:
            self._hwnd = int(form.Handle.ToInt64())
        except Exception:
            self._hwnd = int(form.Handle.ToInt32())
        self._attached = True

        if icon_path is not None and icon_path.is_file():
            try:
                from System.Drawing import Icon

                form.Icon = Icon(str(icon_path))
            except Exception:
                pass

        self._install_borderless_frame()
        self.apply_theme_mode(theme)

    def _install_borderless_frame(self) -> None:
        hwnd = self._hwnd
        if not hwnd:
            return

        def _wnd_proc(h: int, msg: int, w_param: int, l_param: int) -> int:
            if msg == _WM_NCCALCSIZE and w_param:
                params = _NCCALCSIZE_PARAMS.from_address(l_param)
                dpi = int(_GetDpiForWindow(h)) if _GetDpiForWindow is not None else 96
                if dpi <= 0:
                    dpi = 96
                if _GetSystemMetricsForDpi is not None:
                    frame_x = int(_GetSystemMetricsForDpi(_SM_CXFRAME, dpi)) + int(
                        _GetSystemMetricsForDpi(_SM_CXPADDEDBORDER, dpi)
                    )
                    frame_y = int(_GetSystemMetricsForDpi(_SM_CYFRAME, dpi)) + int(
                        _GetSystemMetricsForDpi(_SM_CXPADDEDBORDER, dpi)
                    )
                else:
                    frame_x = int(_user32.GetSystemMetrics(_SM_CXFRAME)) + int(
                        _user32.GetSystemMetrics(_SM_CXPADDEDBORDER)
                    )
                    frame_y = int(_user32.GetSystemMetrics(_SM_CYFRAME)) + int(
                        _user32.GetSystemMetrics(_SM_CXPADDEDBORDER)
                    )

                rect = params.rgrc[0]
                rect.left += frame_x
                rect.right -= frame_x
                rect.bottom -= frame_y
                if _IsZoomed(h):
                    # Compensate maximized over-hang so top bar and taskbar remain exact.
                    rect.top += frame_y
                return 0

            if msg == _WM_NCDESTROY:
                old = self._old_wndproc
                self._old_wndproc = 0
                if old:
                    _CallWindowProc(old, h, msg, w_param, l_param)
                self._wndproc_ref = None
                return 0

            old = self._old_wndproc
            if old:
                return _CallWindowProc(old, h, msg, w_param, l_param)
            return _DefWindowProc(h, msg, w_param, l_param)

        self._wndproc_ref = _WNDPROC(_wnd_proc)
        self._old_wndproc = int(_SetWindowLongPtr(hwnd, _GWLP_WNDPROC, self._wndproc_ref))

        try:
            margins = _MARGINS(0, 0, 1, 0)
            _dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
            corner = ctypes.c_int(_DWMWCP_ROUND)
            _dwmapi.DwmSetWindowAttribute(hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), 4)
        except Exception:
            pass

        _SetWindowPos(
            hwnd,
            None,
            0,
            0,
            0,
            0,
            _SWP_FRAMECHANGED | _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE,
        )

    def _invoke_ui(self, fn) -> bool:
        form = self._form
        if form is None:
            return False
        try:
            if form.IsDisposed:
                return False
            if form.InvokeRequired:
                from System import Action

                form.BeginInvoke(Action(fn))
            else:
                fn()
            return True
        except Exception:
            return False

    def apply_theme_mode(self, theme: str) -> None:
        is_dark = resolve_theme_dark(theme)
        hex_color = "#0b0e14" if is_dark else "#f3f5f8"

        def _apply() -> None:
            if os.name == "nt" and self._hwnd:
                try:
                    dark_val = ctypes.c_int(1 if is_dark else 0)
                    _dwmapi.DwmSetWindowAttribute(
                        self._hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(dark_val), 4
                    )
                except Exception:
                    pass
            form = self._form
            if form is None:
                return
            try:
                from System.Drawing import ColorTranslator

                color = ColorTranslator.FromHtml(hex_color)
                form.BackColor = color
                browser = getattr(form, "browser", None)
                wv = getattr(browser, "webview", None) if browser is not None else None
                if wv is not None:
                    wv.DefaultBackgroundColor = color
            except Exception:
                pass

        self._invoke_ui(_apply)

    def start_drag(self) -> bool:
        if os.name != "nt" or not self._hwnd:
            return False

        def _drag() -> None:
            _user32.ReleaseCapture()
            _SendMessageW(self._hwnd, _WM_NCLBUTTONDOWN, _HTCAPTION, 0)

        return self._invoke_ui(_drag)

    def start_resize(self, edge: str) -> bool:
        if os.name != "nt" or not self._hwnd:
            return False
        hit = _RESIZE_HIT_MAP.get(edge)
        if hit is None:
            return False

        def _resize() -> None:
            _user32.ReleaseCapture()
            _SendMessageW(self._hwnd, _WM_NCLBUTTONDOWN, hit, 0)

        return self._invoke_ui(_resize)

    def minimize(self) -> bool:
        def _min() -> None:
            if self._form is not None:
                import System.Windows.Forms as WinForms

                self._form.WindowState = WinForms.FormWindowState.Minimized

        return self._invoke_ui(_min)

    def window_scale(self) -> float:
        if os.name == "nt" and self._hwnd and _GetDpiForWindow is not None:
            try:
                dpi = int(_GetDpiForWindow(self._hwnd))
                if dpi > 0:
                    return dpi / 96.0
            except OSError:
                pass
        return 1.0

    def physical_to_logical_size(self, width: int, height: int) -> Tuple[int, int]:
        """Convert pywebview resized dimensions to 96-DPI logical startup units."""
        scale = self.window_scale()
        if scale <= 1.0 or _pywebview_major_version() >= 6:
            return int(width), int(height)
        return int(round(width / scale)), int(round(height / scale))

    def is_maximized(self) -> bool:
        if os.name == "nt" and self._hwnd:
            try:
                return bool(_IsZoomed(self._hwnd))
            except Exception:
                pass
        return False

    def is_normal(self) -> bool:
        form = self._form
        if form is None:
            return True
        try:
            import System.Windows.Forms as WinForms

            return form.WindowState == WinForms.FormWindowState.Normal
        except Exception:
            return not self.is_maximized()

    def toggle_maximize(self) -> bool:
        target_max = not self.is_maximized()

        def _toggle() -> None:
            if self._form is None:
                return
            import System.Windows.Forms as WinForms

            self._form.WindowState = (
                WinForms.FormWindowState.Maximized if target_max else WinForms.FormWindowState.Normal
            )

        self._invoke_ui(_toggle)
        return target_max

    def close(self) -> bool:
        def _close() -> None:
            if self._form is not None:
                self._form.Close()

        return self._invoke_ui(_close)
