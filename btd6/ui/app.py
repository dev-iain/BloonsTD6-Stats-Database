from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from functools import partial

from btd6.ui.constants import SPACE_SM
from btd6.ui.palettes import DARK, LIGHT, PALETTES, Palette
from btd6.ui.presenters import SearchPresenter
from btd6.ui.services import load_database, run_query
from btd6.ui.theme import apply_theme, build_fonts
from btd6.ui.views.search_view import SearchView
from btd6.ui.worker import BackgroundRunner, StartThread, start_daemon_thread

WINDOW_TITLE = "BTD6 Tower Stats"


class AppWindow:
    """Composition root: builds theme, view, presenter and worker for one window."""

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
        self.view = SearchView(root, self._fonts, self.dark_mode_var)
        self.runner = BackgroundRunner(root, start_thread=start_thread)
        self.presenter = SearchPresenter(
            self.view,
            self.runner,
            root,
            run_query=partial(run_query, database_path),
            run_load=lambda report: load_database(database_path, report),
        )
        self._finish_layout()

    def _finish_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.view.grid(row=0, column=0, sticky="nsew", padx=SPACE_SM, pady=SPACE_SM)
        self.view.bind_presenter(self.presenter)
        self.view.apply_palette(self._palette)
        self.root.minsize(*self.view.minimum_size())
        self.dark_mode_var.trace_add("write", self._on_dark_mode_changed)
        self.root.bind("<Control-q>", lambda event: self.close())
        self.root.bind("<Alt-d>", lambda event: self.view.dark_toggle.invoke())
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def start(self) -> None:
        self.root.after(0, self.presenter.start)

    def _on_dark_mode_changed(self, *_: object) -> None:
        self.set_palette(DARK if self.dark_mode_var.get() else LIGHT)

    def set_palette(self, palette: Palette) -> None:
        self._palette = PALETTES[palette.name]
        apply_theme(self.root, self._palette, self._fonts)
        self.view.apply_palette(self._palette)

    def close(self) -> None:
        self.presenter.close()
        self.runner.close()
        self.root.destroy()


def create_app(
    root: tk.Tk, database_path: str, on_ready: Callable[[AppWindow], None] | None = None
) -> AppWindow:
    window = AppWindow(root, database_path)
    window.start()
    if on_ready is not None:
        on_ready(window)
    return window
