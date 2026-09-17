"""Real Tk events and geometry regressions for package selection and page sizing."""

import tkinter as tk
from pathlib import Path

import pytest


def show(app, geometry='850x900'):
    app.maxsize(2000, 2000)
    app.geometry(geometry)
    app.deiconify()
    app.update()


def assert_page_at_top(app):
    canvas = app.scroll_area.canvas
    assert canvas.yview() == (0.0, 1.0)
    # yview alone can report (0, 1) even when short content has drifted.
    assert canvas.canvasy(0) == 0
    assert app.scroll_area.content.winfo_rooty() == canvas.winfo_rooty()
    assert not app.scroll_area.scrollbar.winfo_ismapped()


WHEEL_EVENTS = [
    ('<MouseWheel>', {'delta': 120}),
    ('<MouseWheel>', {'delta': -120}),
    ('<MouseWheel>', {'delta': -480}),
    ('<Shift-MouseWheel>', {'delta': -120}),
    ('<Button-4>', {}),
    ('<Button-5>', {}),
]


@pytest.mark.parametrize('attr', ['apk_combo', 'hap_combo'])
@pytest.mark.parametrize('state', ['readonly', 'disabled'])
@pytest.mark.parametrize('sequence,options', WHEEL_EVENTS)
def test_package_wheel_never_changes_selection_or_page(app, attr, state, sequence, options):
    if sequence.startswith('<Button-') and app.tk.call('tk', 'windowingsystem') != 'x11':
        pytest.skip('X11 wheel buttons do not exist on this Tk platform')
    show(app)
    combo = getattr(app, attr)
    combo.configure(values=['first', 'chosen', 'last'], state=state)
    combo.current(1)
    changes = []
    combo.bind('<<ComboboxSelected>>', lambda event: changes.append(combo.get()), add='+')
    combo.focus_force()
    app.update()
    before = app.scroll_area.canvas.yview()
    for _ in range(3):
        combo.event_generate(sequence, **options)
        app.update()
    assert combo.get() == 'chosen'
    assert combo.current() == 1
    assert changes == []
    assert app.scroll_area.canvas.yview() == before


@pytest.mark.parametrize('attr', ['apk_combo', 'hap_combo'])
def test_package_popup_still_scrolls_and_selects_with_keyboard(app, attr):
    show(app)
    combo = getattr(app, attr)
    names = [f'package-{index}.apk' for index in range(30)]
    # The application callback must still resolve a deliberate selection.
    mapping = {name: Path(name) for name in names}
    if attr == 'apk_combo':
        app.apk_name_map = mapping
    else:
        app.hap_name_map = mapping
    combo.configure(values=names, state='readonly')
    combo.current(1)
    combo.focus_force()
    app.update()
    combo.event_generate('<Down>')
    app.update()
    popup = app.tk.call('ttk::combobox::PopdownWindow', str(combo))
    listbox = f'{popup}.f.l'
    try:
        assert app.tk.getboolean(app.tk.call('winfo', 'ismapped', listbox))
        before = app.tk.call(listbox, 'yview')
        app.tk.call('event', 'generate', listbox, '<MouseWheel>', '-delta', -480)
        app.update()
        assert app.tk.call(listbox, 'yview') != before
        assert combo.current() == 1
        app.tk.call('event', 'generate', listbox, '<Control-End>')
        app.tk.call('event', 'generate', listbox, '<Return>')
        app.update()
        assert combo.get() == names[-1]
    finally:
        app.tk.call('ttk::combobox::Unpost', str(combo))


@pytest.mark.parametrize('app', [1.0, 1.5, 2.0], indirect=True)
def test_roomy_page_never_scrolls_away_from_top(app):
    show(app, '1000x1200')
    assert_page_at_top(app)
    for sequence, options in WHEEL_EVENTS[:4]:
        for _ in range(4):
            app.scroll_area.content.event_generate(sequence, **options)
            app.update()
        assert_page_at_top(app)
    app.scroll_area.canvas.focus_force()
    for sequence in ('<Control-End>', '<Control-Next>', '<Control-Home>', '<Control-Prior>'):
        app.scroll_area.canvas.event_generate(sequence)
        app.update()
        assert_page_at_top(app)


@pytest.mark.parametrize('app', [1.0, 1.5, 2.0], indirect=True)
def test_content_growth_and_shrink_update_scroll_region_without_window_resize(app):
    show(app, '850x900')
    assert_page_at_top(app)
    app.device_tree.configure(height=60)
    app.update()
    canvas = app.scroll_area.canvas
    assert canvas.yview()[1] < 1
    assert app.scroll_area.scrollbar.winfo_ismapped()
    app.scroll_area.content.event_generate('<MouseWheel>', delta=-120)
    app.update()
    assert canvas.yview()[0] > 0
    canvas.yview_moveto(1)
    app.update()
    assert canvas.yview()[1] == 1
    app.device_tree.configure(height=3)
    app.update()
    assert_page_at_top(app)


@pytest.mark.parametrize('app', [1.0, 1.5, 2.0], indirect=True)
def test_log_receives_extra_window_height_and_controls_stay_at_top(app):
    show(app, '850x740')
    canvas = app.scroll_area.canvas
    canvas.yview_moveto(0)
    app.update()
    before_height = app.log_text.winfo_height()
    before_top = app.device_tree.winfo_rooty() - canvas.winfo_rooty()
    before_tree_height = app.device_tree.winfo_height()
    show(app, '850x1100')
    assert app.log_text.winfo_height() > before_height + 200
    assert app.device_tree.winfo_rooty() - canvas.winfo_rooty() == before_top
    assert app.device_tree.winfo_height() == before_tree_height
    assert_page_at_top(app)
    # Shrinking and re-enlarging must not retain a stale canvas offset.
    show(app, '480x560')
    canvas.yview_moveto(1)
    app.update()
    show(app, '850x1100')
    assert_page_at_top(app)


def test_log_keeps_independent_scrolling_and_auto_hides_scrollbar_when_it_fits(app):
    show(app, '850x740')
    app.log_text.configure(state=tk.NORMAL)
    app.log_text.delete('1.0', tk.END)
    app.log_text.insert('1.0', '\n'.join(f'line {i}' for i in range(100)))
    app.log_text.configure(state=tk.DISABLED)
    app.log_text.yview_moveto(1)
    app.update()
    page_before = app.scroll_area.canvas.yview()
    text_before = app.log_text.yview()
    app.log_text.event_generate('<MouseWheel>', delta=120)
    app.update()
    assert app.log_text.yview() != text_before
    assert app.scroll_area.canvas.yview() == page_before
    assert app.log_v_scrollbar.winfo_ismapped()
    app.log_text.configure(state=tk.NORMAL)
    app.log_text.delete('1.0', tk.END)
    app.log_text.insert('1.0', 'one line')
    app.log_text.configure(state=tk.DISABLED)
    show(app, '850x1100')
    assert not app.log_v_scrollbar.winfo_ismapped()
    assert not app.log_h_scrollbar.winfo_ismapped()
    assert_page_at_top(app)
