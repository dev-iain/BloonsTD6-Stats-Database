from __future__ import annotations

import tkinter as tk
from functools import partial
from tkinter import ttk
from typing import Any

from btd6.ui.palettes import LIGHT, Palette
from btd6.ui.presenters import SearchPresenter
from btd6.ui.services import list_damage_types, load_database, run_query
from btd6.ui.theme import Fonts, build_fonts
from btd6.ui.views.search_view import SearchView
from btd6.ui.worker import BackgroundRunner, StartThread, start_daemon_thread


class SearchTab(ttk.Frame):
    """The Search notebook page: wires the passive view to its presenter and worker."""

    def __init__(
        self,
        parent: tk.Misc,
        database_path: str,
        fonts: Fonts | None = None,
        dark_mode: tk.BooleanVar | None = None,
        start_thread: StartThread = start_daemon_thread,
    ) -> None:
        super().__init__(parent)
        self.fonts = fonts or build_fonts(parent)
        self.view = SearchView(
            self,
            self.fonts,
            dark_mode or tk.BooleanVar(value=False),
            damage_types=list_damage_types(database_path),
        )
        self.runner = BackgroundRunner(self, start_thread=start_thread)
        self.presenter = SearchPresenter(
            self.view,
            self.runner,
            self,
            run_query=partial(run_query, database_path),
            run_load=lambda report: load_database(database_path, report),
        )
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.view.grid(row=0, column=0, sticky="nsew")
        self.view.bind_presenter(self.presenter)
        self.view.apply_palette(LIGHT)

    @property
    def sort_combobox(self) -> ttk.Combobox:
        return self.view.filter_panel.sort_combobox

    @property
    def damage_type_combobox(self) -> ttk.Combobox:
        return self.view.filter_panel.damage_type_combobox

    @property
    def limit_spinbox(self) -> ttk.Spinbox:
        return self.view.filter_panel.limit_spinbox

    def current_form(self) -> dict[str, Any]:
        return self.view.filter_panel.get_form()

    def apply_palette(self, palette: Palette) -> None:
        self.view.apply_palette(palette)

    def start(self) -> None:
        self.after(0, self.presenter.start)

    def close(self) -> None:
        self.presenter.close()
        self.runner.close()
