from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from btd6.db import connect
from btd6.ui.constants import SPACE_LG, SPACE_SM
from btd6.ui.palettes import DARK, LIGHT, PALETTES, Palette
from btd6.ui.search_tab import SearchTab
from btd6.ui.theme import apply_theme, build_fonts
from btd6.ui.worker import StartThread, start_daemon_thread

WINDOW_TITLE = "BTD6 Tower Stats"
COMING_SOON_TEXT = "Coming soon"
PLACEHOLDER_TABS = ("Rounds", "Rankings")


class AppWindow:
    """Composition root: builds the theme and the notebook of tabs for one window."""

    def __init__(
        self,
        root: tk.Tk,
        database_path: str,
        palette: Palette = LIGHT,
        start_thread: StartThread = start_daemon_thread,
    ) -> None:
        self.root = root
        self._fonts = build_fonts(root)
        self._palette = palette
        self.dark_mode_var = tk.BooleanVar(value=palette is DARK)
        root.title(WINDOW_TITLE)
        apply_theme(root, palette, self._fonts)
        self.notebook = ttk.Notebook(root)
        self.search_tab = SearchTab(
            self.notebook, database_path, self._fonts, self.dark_mode_var, start_thread
        )
        self.view = self.search_tab.view
        self.presenter = self.search_tab.presenter
        self.runner = self.search_tab.runner
        self._add_tabs()
        self._finish_layout()

    def _add_tabs(self) -> None:
        self.notebook.add(self.search_tab, text="Search", underline=0)
        for title in PLACEHOLDER_TABS:
            page = ttk.Frame(self.notebook, padding=SPACE_LG)
            ttk.Label(page, text=COMING_SOON_TEXT, style="Placeholder.TLabel").grid(row=0, column=0)
            page.columnconfigure(0, weight=1)
            page.rowconfigure(0, weight=1)
            self.notebook.add(page, text=title)

    def _finish_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=SPACE_SM, pady=SPACE_SM)
        self.search_tab.apply_palette(self._palette)
        self.root.minsize(*self.view.minimum_size())
        self.dark_mode_var.trace_add("write", self._on_dark_mode_changed)
        self.root.bind("<Control-q>", lambda event: self.close())
        self.root.bind("<Alt-d>", lambda event: self.view.dark_toggle.invoke())
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def start(self) -> None:
        self.search_tab.start()

    def _on_dark_mode_changed(self, *_: object) -> None:
        self.set_palette(DARK if self.dark_mode_var.get() else LIGHT)

    def set_palette(self, palette: Palette) -> None:
        self._palette = PALETTES[palette.name]
        apply_theme(self.root, self._palette, self._fonts)
        self.search_tab.apply_palette(self._palette)

    def close(self) -> None:
        self.search_tab.close()
        self.root.destroy()


def create_app(
    root: tk.Tk, database_path: str, on_ready: Callable[[AppWindow], None] | None = None
) -> AppWindow:
    window = AppWindow(root, database_path)
    window.start()
    if on_ready is not None:
        on_ready(window)
    return window


def build_window(database_path: str) -> tk.Tk:
    """Create the root window with every tab and start the first search."""
    root = tk.Tk()
    try:
        AppWindow(root, database_path).start()
    except Exception:
        root.destroy()
        raise
    return root


def main(database_path: str) -> int:
    """Run the desktop app until its window closes; the connection closes with it."""
    root = build_window(database_path)
    connection = connect(database_path)
    try:
        root.mainloop()
    finally:
        connection.close()
    return 0
