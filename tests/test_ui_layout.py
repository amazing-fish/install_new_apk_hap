import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main


def test_app_window_is_compact_and_package_fields_are_scrollable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(main, "detect_devices", lambda: [])

    app = main.App()
    try:
        app.update()

        assert app.geometry().startswith("380x700")
        assert app.minsize() == (380, 600)
        assert hasattr(app, "apk_display_entry")
        assert hasattr(app, "hap_display_entry")
        assert str(app.apk_display_entry.cget("state")) == "readonly"
        assert str(app.hap_display_entry.cget("state")) == "readonly"
        assert app.apk_combo.winfo_width() > app.apk_display_entry.winfo_width()
        assert app.hap_combo.winfo_width() > app.hap_display_entry.winfo_width()
        assert app.device_tree.column("name", option="width") <= 100
        assert hasattr(app, "save_name_button")
        assert hasattr(app, "copy_device_button")
        assert app.save_name_button.winfo_rooty() == app.name_entry.winfo_rooty()
        assert app.copy_device_button.cget("text") == "设备码"
        assert app.copy_device_button.winfo_height() <= 28

        app.geometry("380x600")
        app.update()

        assert hasattr(app, "main_canvas")
        assert hasattr(app, "main_scrollbar")
        assert app.main_canvas.bbox("all")[3] > app.main_canvas.winfo_height()
        assert app.main_canvas.yview()[1] < 1.0

        app.main_canvas.yview_moveto(1.0)
        app.update()

        assert app.main_canvas.yview()[0] > 0.0
    finally:
        app.destroy()
