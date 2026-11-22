"""Desktop entry point: launches PyWebView (Edge WebView2) + native drag-and-drop, or runs CLI diagnostics."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import uuid
from typing import Optional

# Ensure `backend/` is importable when invoked as `python backend/main.py`.
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from bridge import InstallerBridge, JsApiFacade
from win_window import NativeWindowController, compute_initial_window_size, theme_background_color


def _web_dist_index() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", BACKEND_DIR))
        return base / "web_dist" / "index.html"
    return BACKEND_DIR / "web_dist" / "index.html"


def _app_icon_path() -> Optional[Path]:
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "assets" / "app_icon.ico" if getattr(sys, "frozen", False) else None,
        BACKEND_DIR / "assets" / "app_icon.ico",
    ]
    for path in candidates:
        if path and path.is_file():
            return path
    return None


def _webview_storage_dir() -> str:
    """Persistent WebView2 profile directory to reuse browser engine & V8 bytecode cache."""
    if os.name == "nt":
        for var in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(var, "").strip()
            if base:
                path = Path(base) / "install_new_apk_hap" / "webview2"
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    if os.access(path, os.W_OK):
                        return str(path)
                except OSError:
                    pass
    path = Path(tempfile.gettempdir()) / "install_new_apk_hap_webview2"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _select_http_port(preferred: int = 42001) -> int:
    """Reuse preferred origin port when idle for WebView2 cache hits; otherwise pick ephemeral port."""
    for target_port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", target_port))
                return int(sock.getsockname()[1])
            except OSError:
                continue
    return 0


def _build_fast_server_class():
    """Create a BottleServer subclass that skips reverse DNS lookups and caches hashed assets."""
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server
    import bottle
    import webview
    import webview.http as webview_http

    class FastThreadedAdapter(bottle.ServerAdapter):
        def run(self, handler) -> None:
            class QuietNoDnsHandler(WSGIRequestHandler):
                def address_string(self) -> str:
                    return self.client_address[0]

                def log_request(self, *args, **kwargs) -> None:
                    if not self.quiet:
                        super().log_request(*args, **kwargs)

            QuietNoDnsHandler.quiet = bool(self.quiet)

            class ThreadAdapter(ThreadingMixIn, WSGIServer):
                daemon_threads = True

            self.options["handler_class"] = QuietNoDnsHandler
            srv = make_server(self.host, self.port, handler, server_class=ThreadAdapter, **self.options)
            srv.serve_forever()

    class FastLocalServer(webview_http.BottleServer):
        @classmethod
        def start_server(cls, urls, http_port, keyfile=None, certfile=None):
            if keyfile and certfile:
                return super().start_server(urls, http_port, keyfile=keyfile, certfile=certfile)

            apps = [u for u in urls if webview_http.is_app(u)]
            if apps:
                return super().start_server(urls, http_port, keyfile=keyfile, certfile=certfile)

            server = cls()
            server.uid = str(uuid.uuid1())
            local_urls = [u.split("#")[0] for u in urls if webview_http.is_local_url(u)]
            common_path = os.path.commonpath(local_urls) if local_urls else None
            if common_path is not None and not os.path.isdir(webview_http.abspath(common_path)):
                common_path = os.path.dirname(common_path)
            server.root_path = webview_http.abspath(common_path) if common_path is not None else None

            app = bottle.Bottle()

            @app.post(f"/js_api/{server.uid}")
            def js_api():
                bottle.response.headers["Access-Control-Allow-Origin"] = "*"
                bottle.response.headers["Access-Control-Allow-Methods"] = "PUT, GET, POST, DELETE, OPTIONS"
                bottle.response.headers["Access-Control-Allow-Headers"] = (
                    "Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token"
                )
                body = json.loads(bottle.request.body.read().decode("utf-8"))
                if body["uid"] in server.js_callback:
                    return json.dumps(server.js_callback[body["uid"]](body))
                return ""

            @app.route("/")
            @app.route("/<file:path>")
            def asset(file: str = "index.html"):
                if not server.root_path:
                    return ""
                if file.startswith("assets/"):
                    bottle.response.set_header("Cache-Control", "public, max-age=31536000, immutable")
                else:
                    bottle.response.set_header("Cache-Control", "no-cache")
                return bottle.static_file(file, root=server.root_path)

            server.port = http_port or _select_http_port()
            quiet = not webview._state["debug"]
            server.thread = threading.Thread(
                target=lambda: bottle.run(
                    app=app,
                    host="127.0.0.1",
                    server=FastThreadedAdapter,
                    port=server.port,
                    quiet=quiet,
                ),
                daemon=True,
            )
            server.thread.start()
            server.running = True
            server.address = f"http://127.0.0.1:{server.port}/"
            cls.common_path = common_path
            server.js_api_endpoint = f"{server.address}js_api/{server.uid}"
            return server.address, common_path, server

    return FastLocalServer


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
    cfg = bridge.config_manager.data
    theme = str(cfg.get("theme", "system"))
    init_width, init_height, min_size = compute_initial_window_size(
        cfg.get("window_width"),
        cfg.get("window_height"),
    )

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

    window_controller = NativeWindowController()
    icon_path = _app_icon_path()
    last_normal_size: list[Optional[tuple[int, int]]] = [None]

    window = webview.create_window(
        title="APK / HAP 安装工具",
        url=target_url,
        js_api=JsApiFacade(bridge),
        width=init_width,
        height=init_height,
        min_size=min_size,
        background_color=theme_background_color(theme),
        text_select=True,
    )
    bridge.attach_window(window)
    bridge.attach_window_controller(window_controller)

    def _on_before_show():
        window_controller.attach(window, icon_path, theme)

    def _on_loaded():
        _bind_native_drop(window, bridge)
        bridge.notify_window_state(window_controller.is_maximized())

    def _on_resized(width, height):
        if window_controller.is_normal() and isinstance(width, int) and isinstance(height, int):
            if width >= min_size[0] and height >= min_size[1]:
                last_normal_size[0] = (width, height)

    def _on_maximized():
        bridge.notify_window_state(True)

    def _on_restored():
        bridge.notify_window_state(False)

    def _on_closing():
        if last_normal_size[0] is not None:
            try:
                bridge.config_manager.set_window_size(*last_normal_size[0])
            except Exception:
                pass
        bridge.close()

    def _on_closed():
        bridge.close()

    window.events.before_show += _on_before_show
    window.events.loaded += _on_loaded
    window.events.resized += _on_resized
    window.events.maximized += _on_maximized
    window.events.restored += _on_restored
    window.events.closing += _on_closing
    window.events.closed += _on_closed

    gui_backend = "edgechromium" if os.name == "nt" else None
    http_port = _select_http_port() if use_http_server else None
    fast_server = _build_fast_server_class() if use_http_server else webview.http.BottleServer
    webview.start(
        gui=gui_backend,
        http_server=use_http_server,
        http_port=http_port,
        private_mode=False,
        storage_path=_webview_storage_dir(),
        server=fast_server,
        debug=debug,
    )
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
