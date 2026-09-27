import builtins
import json
import tkinter as tk
from tkinter import font as tkfont, ttk

import pytest

import main
import ui_styles
from services.package_metadata_cli import run_cli


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
    assert json.loads(output.read_text(encoding='utf8')) == {
        'themed': True, 'theme': ui_styles.THEME_NAME}


def test_theme_report_rejects_package_paths(tmp_path, capsys):
    with pytest.raises(SystemExit):
        run_cli(['--theme-report', str(tmp_path / 'theme.json'), 'demo.apk'])
    assert '--theme-report' in capsys.readouterr().err
