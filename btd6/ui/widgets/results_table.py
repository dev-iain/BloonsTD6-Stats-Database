from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from btd6.ui.constants import SPACE_LG, SPACE_SM
from btd6.ui.palettes import Palette
from btd6.ui.presenters import TABLE_COLUMNS, ColumnSpec
from btd6.ui.theme import Fonts
from btd6.ui.widgets.tooltip import TooltipWindow

ASCENDING_MARK = " ▲"
DESCENDING_MARK = " ▼"
ZEBRA_TAGS = ("even", "odd")


class ResultsTable(ttk.Frame):
    """Scrollable, sortable results grid. Emits column keys; holds no query logic."""

    def __init__(
        self,
        parent: tk.Misc,
        fonts: Fonts,
        on_sort: Callable[[str], None],
        on_load: Callable[[], None],
        columns: tuple[ColumnSpec, ...] = TABLE_COLUMNS,
    ) -> None:
        super().__init__(parent)
        self._columns = columns
        self._on_sort = on_sort
        self._sort_key: str | None = None
        self._descending = False
        self._tooltip = TooltipWindow(self)
        self._tooltip_key: str | None = None
        self._build_tree(fonts)
        self._build_placeholder(on_load)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    def _build_tree(self, fonts: Fonts) -> None:
        column_keys = [spec.key for spec in self._columns]
        self._tree = ttk.Treeview(
            self, columns=column_keys, show="headings", selectmode="browse", style="Stats.Treeview"
        )
        vertical = ttk.Scrollbar(
            self, orient="vertical", command=self._tree.yview, style="Stats.Vertical.TScrollbar"
        )
        horizontal = ttk.Scrollbar(
            self,
            orient="horizontal",
            command=self._tree.xview,
            style="Stats.Horizontal.TScrollbar",
        )
        self._tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self._configure_columns(fonts)
        self._tree.bind("<Motion>", self._on_motion)
        self._tree.bind("<Leave>", self._hide_tooltip)

    def _configure_columns(self, fonts: Fonts) -> None:
        for spec in self._columns:
            self._tree.heading(spec.key, text=self._heading_text(spec), anchor=self._anchor(spec))
            if spec.sortable:
                self._tree.heading(
                    spec.key, command=lambda column_key=spec.key: self._on_sort(column_key)
                )
            width = self._column_width(spec, fonts)
            self._tree.column(
                spec.key,
                width=width,
                minwidth=width,
                anchor=self._anchor(spec),
                stretch=spec.key == self._columns[-1].key,
            )

    @staticmethod
    def _column_width(spec: ColumnSpec, fonts: Fonts) -> int:
        cell_width = fonts.monospace.measure("0") * spec.width_chars
        marked = spec.heading + DESCENDING_MARK
        heading_width = fonts.heading.measure(marked) + 3 * SPACE_SM
        return max(cell_width, heading_width)

    @staticmethod
    def _anchor(spec: ColumnSpec) -> str:
        return "e" if spec.numeric else "w"

    def _heading_text(self, spec: ColumnSpec) -> str:
        if spec.key != self._sort_key:
            return spec.heading
        return spec.heading + (DESCENDING_MARK if self._descending else ASCENDING_MARK)

    def _build_placeholder(self, on_load: Callable[[], None]) -> None:
        self._placeholder = ttk.Frame(self, style="Placeholder.TFrame", padding=SPACE_LG)
        self._placeholder_label = ttk.Label(
            self._placeholder, style="Placeholder.TLabel", anchor="center", wraplength=0
        )
        self._load_button = ttk.Button(
            self._placeholder,
            text="Load tower data",
            underline=0,
            style="Action.TButton",
            command=on_load,
        )
        self._placeholder.columnconfigure(0, weight=1)
        self._placeholder.rowconfigure((0, 3), weight=1)
        self._placeholder_label.grid(row=1, column=0, pady=SPACE_SM)
        self._load_button.grid(row=2, column=0, pady=SPACE_SM)
        self._placeholder.bind("<Configure>", self._fit_wraplength)

    def _fit_wraplength(self, event: tk.Event) -> None:
        self._placeholder_label.configure(wraplength=max(event.width - 2 * SPACE_LG, 0))

    def set_rows(self, rows: list[tuple[str, ...]]) -> None:
        self._hide_placeholder()
        self._clear_rows()
        for index, result_row in enumerate(rows):
            self._tree.insert("", "end", values=result_row, tags=(ZEBRA_TAGS[index % 2],))
        self._tree.yview_moveto(0)

    def _clear_rows(self) -> None:
        self._tree.delete(*self._tree.get_children())

    def show_placeholder(self, message: str, offer_load: bool) -> None:
        self._clear_rows()
        self._placeholder_label.configure(text=message)
        if offer_load:
            self._load_button.grid()
        else:
            self._load_button.grid_remove()
        self._placeholder.grid(row=0, column=0, sticky="nsew")
        self._placeholder.lift()

    def _hide_placeholder(self) -> None:
        self._placeholder.grid_remove()

    def set_load_enabled(self, enabled: bool) -> None:
        self._load_button.state(["!disabled"] if enabled else ["disabled"])

    def set_sort_indicator(self, column_key: str | None, descending: bool) -> None:
        self._sort_key = column_key
        self._descending = descending
        for spec in self._columns:
            self._tree.heading(spec.key, text=self._heading_text(spec))

    def apply_palette(self, palette: Palette) -> None:
        self._tree.tag_configure("even", background=palette.color_surface)
        self._tree.tag_configure("odd", background=palette.color_surface_alt)

    def row_values(self) -> list[tuple[str, ...]]:
        return [tuple(self._tree.item(item, "values")) for item in self._tree.get_children()]

    def _hide_tooltip(self, event: tk.Event) -> None:
        self._tooltip.hide()
        self._tooltip_key = None

    def _on_motion(self, event: tk.Event) -> None:
        if self._tree.identify_region(event.x, event.y) != "heading":
            self._tooltip.hide()
            return
        spec = self._column_at(event.x)
        if spec is None or not spec.hint:
            self._tooltip.hide()
            self._tooltip_key = None
        elif spec.key != self._tooltip_key:
            self._tooltip_key = spec.key
            self._tooltip.show(spec.hint, event.x_root, event.y_root)

    def _column_at(self, x_position: int) -> ColumnSpec | None:
        column_id = self._tree.identify_column(x_position)
        index = int(column_id.lstrip("#")) - 1
        return self._columns[index] if 0 <= index < len(self._columns) else None
