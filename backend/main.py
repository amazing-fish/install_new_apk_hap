"""Desktop entry point: launches PyWebView (Edge WebView2) + native drag-and-drop, or runs CLI diagnostics."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Optional

# Ensure `backend/` is importable when invoked as `python backend/main.py`.
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from bridge import InstallerBridge


def _web_dist_index() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", BACKEND_DIR))
        return base / "web_dist" / "index.html"
    return BACKEND_DIR / "web_dist" / "index.html"


def _bind_native_drop(window, bridge: InstallerBridge) -> None:
    """Attach PyWebView DOM drop listener to extract native OS file paths."""
    try:
        from webview.dom import DOMEventHandler

        def on_drop(event):
            try:
                files = event.get("dataTransfer", {}).get("files", [])
                paths = [f.get("pywebviewFullPath") for f in files if isinstance(f, dict) and f.get("pywebviewFullPath")]
                if paths:
                    bridge.handle_dropped_paths(paths)
            except Exception:
                pass

        window.dom.document.events.drop += DOMEventHandler(on_drop, prevent_default=True, stop_propagation=False)
    except Exception:
        pass


def launch_desktop(dev_url: Optional[str] = None, debug: bool = False) -> int:
    import webview

    bridge = InstallerBridge()
    if dev_url:
        target_url = dev_url
        use_http_server = False
    else:
        index_path = _web_dist_index()
        if not index_path.is_file():
            raise FileNotFoundError(
                f"未找到前端构建产物：{index_path}\n"
                "请先执行 `cd frontend && npm install && npm run build`，或通过 `--dev-url http://localhost:5173` 启动开发模式。"
            )
        target_url = str(index_path)
        use_http_server = True

    window = webview.create_window(
        title="APK / HAP 安装工具",
        url=target_url,
        js_api=bridge,
        width=1080,
        height=780,
        min_size=(760, 580),
        text_select=True,
    )
    bridge.attach_window(window)

    def _on_loaded():
        _bind_native_drop(window, bridge)

    def _on_closing():
        bridge.close()

    def _on_closed():
        bridge.close()

    window.events.loaded += _on_loaded
    window.events.closing += _on_closing
    window.events.closed += _on_closed

    gui_backend = "edgechromium" if os.name == "nt" else None
    webview.start(gui=gui_backend, http_server=use_http_server, debug=debug)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] in ("--package-label-report", "--tool-notices", "--env-check"):
        from cli import run_cli

        return run_cli(argv[1:])

    dev_url = os.environ.get("INSTALLER_DEV_URL", "").strip() or None
    debug = os.environ.get("INSTALLER_DEBUG", "") == "1"
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--dev-url" and i + 1 < len(argv):
            dev_url = argv[i + 1]
            i += 2
            continue
        if arg == "--debug":
            debug = True
            i += 1
            continue
        i += 1

    return launch_desktop(dev_url=dev_url, debug=debug)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
