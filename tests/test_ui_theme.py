import builtins
import json
import tkinter as tk
from tkinter import font as tkfont, ttk

import pytest

import ui_styles
from cli import run_cli


def test_sun_valley_theme_is_active(app):
    style = ttk.Style(app)
    assert style.theme_use() == ui_styles.THEME_NAME
    # The install action is the single accent (primary) button.
    assert style.layout('Primary.TButton') == style.layout('Accent.TButton')
    assert str(app.install_button.cget('style')) == 'Primary.TButton'


def test_style_colours_survive_later_theme_events(app):
    # sv-ttk recolours widgets via tk_setPalette on <<ThemeChanged>>; that must
    # not overwrite the hint colour or the log border once widgets exist.
    hint = ttk.Label(app, text='hint', style='Hint.TLabel')
    app.event_generate('<<ThemeChanged>>')
    app.update()
    assert str(hint.cget('foreground')) == ''
    assert ttk.Style(app).lookup('Hint.TLabel', 'foreground') == ui_styles.HINT_FOREGROUND
    assert str(app.log_text.cget('highlightbackground')) == ui_styles.BORDER_COLOR
    assert str(app.log_text.cget('highlightcolor')) == ui_styles.ACCENT_COLOR


def test_theme_fonts_follow_display_scale(app):
    body = tkfont.nametofont('SunValleyBodyFont', root=app)
    assert body.actual('family') == tkfont.nametofont('TkDefaultFont', root=app).actual('family')
    assert int(body.cget('size')) == round(-14 * ui_styles.ui_scale(app))


@pytest.mark.parametrize('app', [1.67], indirect=True)
def test_initial_fit_keeps_display_scaled_width(app):
    # Once the tree has stretched to the window, the fit must not shrink the
    # window back to the unscaled baseline columns.
    app.attributes('-alpha', 0)
    app.geometry('1200x900')
    app.deiconify()
    app.update()
    ui_styles.fit_initial_window(app, app.device_tree)
    app.update()
    assert app.winfo_width() >= ui_styles.scaled_default_width(app) > 590


@pytest.fixture
def no_sv_ttk(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == 'sv_ttk':
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', fake_import)


def test_native_theme_fallback_without_sv_ttk(no_sv_ttk, app):
    style = ttk.Style(app)
    assert style.theme_use() != ui_styles.THEME_NAME
    assert style.lookup('Hint.TLabel', 'foreground') == ui_styles.HINT_FOREGROUND
    assert str(app.log_text.cget('relief')) == 'solid'
    assert app.install_button.winfo_exists()


def test_theme_report_cli(tmp_path):
    output = tmp_path / 'theme.json'
    assert run_cli(['--theme-report', str(output)]) == 0
    report = json.loads(output.read_text(encoding='utf8'))
    assert report.pop('tile_fix_sprites') > 0
    assert report == {'themed': True, 'theme': ui_styles.THEME_NAME}


def themed_sizes(monkeypatch, tile_fix):
    """Requested sizes of stretched sv-ttk controls in a fresh interpreter."""
    monkeypatch.setenv('INSTALL_APK_HAP_TILE_FIX', '1' if tile_fix else '0')
    window = tk.Tk()
    window.withdraw()
    try:
        assert ui_styles.apply_theme(window)
        widgets = [
            ttk.Button(window, text='按钮'),
            ttk.Button(window, text='安装', style='Primary.TButton'),
            ttk.Entry(window),
            ttk.Combobox(window, values=['a.apk']),
            ttk.Checkbutton(window, text='勾选'),
            ttk.Menubutton(window, text='菜单'),
            ttk.Scrollbar(window),
            ttk.Treeview(window, height=2),
        ]
        for widget in widgets:
            widget.pack()
        window.update_idletasks()
        return getattr(window, 'tile_fix_sprites', 0), [
            (widget.winfo_class(), widget.winfo_reqwidth(), widget.winfo_reqheight())
            for widget in widgets]
    finally:
        window.destroy()


def test_tile_fix_keeps_natural_sizes(monkeypatch):
    # Widened sprites draw with fewer tiles (#84); the natural size must still
    # come from the original sprite, or every control would grow.
    widened, fixed = themed_sizes(monkeypatch, tile_fix=True)
    unfixed, plain = themed_sizes(monkeypatch, tile_fix=False)
    assert widened > 0 and unfixed == 0
    assert fixed == plain


def test_tile_fix_sprites_are_widened_only_along_stretch_axes(app):
    images = app.tk.splitlist(app.tk.call('array', 'get', '::ttk::theme::sv_light::I'))
    sizes = {name: (int(app.tk.call('image', 'width', image)),
                    int(app.tk.call('image', 'height', image)))
             for name, image in zip(images[::2], images[1::2])}
    # Button/entry frames stretch both ways; scrollbar parts along their length
    # only; check and radio indicators are drawn at their own size.
    assert sizes['button-rest'] == sizes['textbox-rest'] == ui_styles.TILE_TARGET_SIZE
    assert sizes['scrollbar-thumb-vert'] == (12, 64)
    assert sizes['scrollbar-thumb-hor'] == (320, 12)
    assert sizes['check-rest'] == sizes['radio-rest'] == (20, 20)


def test_theme_report_rejects_package_paths(tmp_path, capsys):
    with pytest.raises(SystemExit):
        run_cli(['--theme-report', str(tmp_path / 'theme.json'), 'demo.apk'])
    assert '--theme-report' in capsys.readouterr().err
