"""Layout helpers with window-scoped bindings; no application state or tasks."""

import tkinter as tk
from tkinter import ttk


class ScrollableArea(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, width=1, height=1)
        self.scrollbar = ttk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.content = ttk.Frame(self.canvas, padding=(12, 8))
        self._window = self.canvas.create_window(0, 0, window=self.content, anchor=tk.NW)
        self.content.bind('<Configure>', self._content_changed)
        self.canvas.bind('<Configure>', self._viewport_changed)
        self._root_window = self.winfo_toplevel()
        self._bindings = []
        for sequence, callback in (
            ('<MouseWheel>', self._wheel), ('<Button-4>', self._wheel),
            ('<Button-5>', self._wheel), ('<FocusIn>', self._focus_changed),
            ('<Control-Home>', lambda event: self._move(0)),
            ('<Control-End>', lambda event: self._move(1)),
            ('<Control-Prior>', lambda event: self._page(-1)),
            ('<Control-Next>', lambda event: self._page(1)),
        ):
            self._bindings.append((sequence, self._root_window.bind(sequence, callback, add='+')))

    def _content_changed(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox(self._window))

    def _viewport_changed(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _contains(self, widget):
        while isinstance(widget, tk.Misc):
            if widget is self:
                return True
            widget = widget.master
        return False

    def _wheel(self, event):
        if not self._contains(event.widget):
            return
        # Let nested controls keep their native wheel/selection behavior.
        if event.widget.winfo_class() in ('Text', 'Treeview', 'TCombobox', 'TScrollbar'):
            return
        delta = getattr(event, 'delta', 0)
        direction = -1 if getattr(event, 'num', None) == 4 or delta > 0 else 1
        self.canvas.yview_scroll(direction * max(1, abs(int(delta / 120))) * 3, 'units')
        return 'break'

    def _focus_changed(self, event):
        if self._contains(event.widget):
            self.reveal(event.widget)

    def reveal(self, widget):
        """Expose the focused control without changing its own scroll position."""
        self.update_idletasks()
        top = widget.winfo_rooty() - self.content.winfo_rooty()
        bottom = top + widget.winfo_height()
        visible_top = self.canvas.canvasy(0)
        height = self.canvas.winfo_height()
        if top < visible_top or bottom - top > height:
            target = top
        elif bottom > visible_top + height:
            target = bottom - height
        else:
            return
        self.canvas.yview_moveto(max(0, target) / max(1, self.content.winfo_height()))

    def _move(self, fraction):
        self.canvas.yview_moveto(fraction)
        return 'break'

    def _page(self, direction):
        self.canvas.yview_scroll(direction, 'pages')
        return 'break'

    def destroy(self):
        for sequence, identifier in self._bindings:
            self._root_window.unbind(sequence, identifier)
        super().destroy()


class ActionRow(ttk.Frame):
    """Reflow actions by their requested widths, including the active Tk scale."""
    def __init__(self, parent):
        super().__init__(parent)
        self.buttons = []
        self.bind('<Configure>', self._arrange)

    def add(self, text, command):
        button = ttk.Button(self, text=text, command=command)
        self.buttons.append(button)
        button.grid(row=len(self.buttons)-1, column=0, sticky=tk.EW, padx=2, pady=3)
        return button

    def _arrange(self, event):
        if not self.buttons:
            return
        required = max(button.winfo_reqwidth() for button in self.buttons) + 4
        columns = max(1, min(len(self.buttons), event.width // required))
        for index, button in enumerate(self.buttons):
            button.grid(row=index // columns, column=index % columns)
        for column in range(len(self.buttons)):
            self.columnconfigure(column, weight=1 if column < columns else 0)
