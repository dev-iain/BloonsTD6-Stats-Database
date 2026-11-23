from __future__ import annotations

import tkinter as tk
from collections.abc import Sequence
from tkinter import ttk
from typing import Protocol

from btd6.ui.constants import SPACE_MD, SPACE_SM
from btd6.ui.palettes import Palette
from btd6.ui.presenters import TABLE_COLUMNS, FilterInputs
from btd6.ui.theme import Fonts
from btd6.ui.widgets.filter_panel import FilterPanel
from btd6.ui.widgets.results_table import ResultsTable

MIN_TABLE_CHARS = 40


class SearchPresenterPort(Protocol):
    def on_filters_changed(self, inputs: FilterInputs) -> None: ...

    def on_submit(self, inputs: FilterInputs) -> None: ...

    def reset(self) -> None: ...

    def on_sort(self, column: str) -> None: ...

    def on_sort_selected(self, column: str | None) -> None: ...

    def load_database(self) -> None: ...


class SearchView(ttk.Frame):
    """Passive screen: renders presenter output and forwards user events to it."""

    def __init__(
        self,
        parent: tk.Misc,
        fonts: Fonts,
        on_dark_mode: tk.BooleanVar,
        damage_types: Sequence[str] = (),
    ) -> None:
        super().__init__(parent, padding=SPACE_MD)
        self._fonts = fonts
        self._damage_types = damage_types
        self._presenter: SearchPresenterPort | None = None
        self.status_var = tk.StringVar()
        self.status_is_error = False
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_toolbar(on_dark_mode)
        self._build_body()
        self._build_status_bar()

    def bind_presenter(self, presenter: SearchPresenterPort) -> None:
        self._presenter = presenter
        self._bind_shortcuts()

    def _make_bar(self, row: int, pady: tuple[int, int]) -> ttk.Frame:
        bar = ttk.Frame(self)
        bar.grid(row=row, column=0, columnspan=2, sticky="ew", pady=pady)
        bar.columnconfigure(0, weight=1)
        return bar

    def _build_toolbar(self, dark_mode: tk.BooleanVar) -> None:
        toolbar = self._make_bar(0, (0, SPACE_SM))
        ttk.Label(toolbar, text="BTD6 Tower Stats", style="Heading.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.dark_toggle = ttk.Checkbutton(
            toolbar, text="Dark mode", underline=0, variable=dark_mode, style="Toolbar.TCheckbutton"
        )
        self.dark_toggle.grid(row=0, column=1, sticky="e")

    def _build_body(self) -> None:
        self.filter_panel = FilterPanel(
            self,
            on_change=lambda inputs: self._presenter.on_filters_changed(inputs),
            on_submit=lambda inputs: self._presenter.on_submit(inputs),
            on_reset=lambda: self._presenter.reset(),
            on_sort_selected=lambda column: self._presenter.on_sort_selected(column),
            damage_types=self._damage_types,
        )
        self.results_table = ResultsTable(
            self,
            self._fonts,
            on_sort=lambda column: self._presenter.on_sort(column),
            on_load=lambda: self._presenter.load_database(),
        )
        self.filter_panel.grid(row=1, column=0, sticky="ns", padx=(0, SPACE_MD))
        self.results_table.grid(row=1, column=1, sticky="nsew")

    def _build_status_bar(self) -> None:
        status_bar = self._make_bar(2, (SPACE_SM, 0))
        self.status_label = ttk.Label(
            status_bar, textvariable=self.status_var, style="Status.TLabel"
        )
        self.progress = ttk.Progressbar(
            status_bar, mode="indeterminate", length=120, style="Status.Horizontal.TProgressbar"
        )
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.progress.grid(row=0, column=1, sticky="e", padx=(SPACE_MD, 0))

    def _bind_shortcuts(self) -> None:
        window = self.winfo_toplevel()
        window.bind("<Alt-s>", lambda event: self.filter_panel.search_button.invoke())
        window.bind("<Alt-r>", lambda event: self.filter_panel.reset_button.invoke())
        window.bind("<Alt-n>", lambda event: self.filter_panel.focus_name())
        window.bind("<Control-f>", lambda event: self.filter_panel.focus_name())
        window.bind("<Alt-l>", lambda event: self._presenter.load_database())
        for position, spec in enumerate(TABLE_COLUMNS, start=1):
            window.bind(
                f"<Control-Key-{position}>",
                lambda event, column_key=spec.key: self._sort(column_key),
            )

    def _sort(self, column_key: str) -> None:
        self._presenter.on_sort(column_key)

    def minimum_size(self) -> tuple[int, int]:
        self.update_idletasks()
        table_width = self._fonts.monospace.measure("0") * MIN_TABLE_CHARS
        return self.filter_panel.winfo_reqwidth() + table_width, self.winfo_reqheight()

    def apply_palette(self, palette: Palette) -> None:
        self.results_table.apply_palette(palette)

    def show_rows(self, rows: list[tuple[str, ...]]) -> None:
        self.results_table.set_rows(rows)

    def show_placeholder(self, message: str, offer_load: bool) -> None:
        self.results_table.show_placeholder(message, offer_load)

    def show_status(self, message: str, is_error: bool) -> None:
        self.status_var.set(message)
        self.status_is_error = is_error
        self.status_label.configure(style="StatusError.TLabel" if is_error else "Status.TLabel")

    def set_busy(self, busy: bool) -> None:
        self.configure(cursor="watch" if busy else "")
        self.results_table.set_load_enabled(not busy)
        if busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)

    def show_field_errors(self, errors: dict[str, str]) -> None:
        self.filter_panel.set_errors(errors)

    def show_sort(self, column: str | None, descending: bool) -> None:
        self.filter_panel.set_sort(column)
        self.results_table.set_sort_indicator(column, descending)

    def show_filters(self, inputs: FilterInputs) -> None:
        self.filter_panel.set_inputs(inputs)
