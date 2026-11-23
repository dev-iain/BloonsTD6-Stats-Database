from __future__ import annotations

import re
import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from btd6.query import POP_PROPERTIES, SORT_COLUMNS
from btd6.ui.constants import SPACE_SM, SPACE_XS
from btd6.ui.presenters import THRESHOLD_FIELDS, FilterInputs, PopChoice

NUMBER_PATTERN = re.compile(r"^\d*\.?\d*$")
WHOLE_NUMBER_PATTERN = re.compile(r"^\d*$")
ANY_DAMAGE_TYPE = "Any"
MAX_LIMIT = 9999
CAMO_FORM_VALUES = {PopChoice.ANY: "either", PopChoice.CAN: "yes", PopChoice.CANNOT: "no"}
FORM_KEYS = {"min_projectile_speed": "min_speed"}
CHOICE_LABELS = ((PopChoice.ANY, "Any"), (PopChoice.CAN, "Can"), (PopChoice.CANNOT, "Cannot"))
CAMO_ROW = "camo"
ENTRY_WIDTH_CHARS = 10
NAME_ENTRY_WIDTH_CHARS = 24


def is_partial_number(proposed: str) -> bool:
    return NUMBER_PATTERN.match(proposed) is not None


def is_partial_whole_number(proposed: str) -> bool:
    return WHOLE_NUMBER_PATTERN.match(proposed) is not None


class FilterPanel(ttk.Frame):
    """Filter inputs mirroring `UpgradeFilters`. Emits `FilterInputs`; never queries."""

    def __init__(
        self,
        parent: tk.Misc,
        on_change: Callable[[FilterInputs], None],
        on_submit: Callable[[FilterInputs], None],
        on_reset: Callable[[], None],
        on_sort_selected: Callable[[str | None], None] | None = None,
        damage_types: Sequence[str] = (),
    ) -> None:
        super().__init__(parent, padding=SPACE_SM)
        self._on_change = on_change
        self._on_submit = on_submit
        self._on_reset = on_reset
        self._on_sort_selected = on_sort_selected
        self._damage_types = (ANY_DAMAGE_TYPE, *damage_types)
        self._muted = False
        self._number_check = (self.register(is_partial_number), "%P")
        self._whole_number_check = (self.register(is_partial_whole_number), "%P")
        self.name_var = tk.StringVar()
        self.damage_type_var = tk.StringVar(value=ANY_DAMAGE_TYPE)
        self.sort_var = tk.StringVar()
        self.limit_var = tk.StringVar()
        self.choice_vars = {name: tk.StringVar(value=PopChoice.ANY) for name in POP_PROPERTIES}
        self.choice_vars[CAMO_ROW] = tk.StringVar(value=PopChoice.ANY)
        self.threshold_vars = {name: tk.StringVar() for name in THRESHOLD_FIELDS}
        self._error_labels: dict[str, ttk.Label] = {}
        self._entries: dict[str, ttk.Entry] = {}
        self.columnconfigure(0, weight=1)
        self._build_name_group()
        self._build_pop_group()
        self._build_threshold_group()
        self._build_options_group()
        self._build_buttons()
        self._watch_variables()

    def _build_name_group(self) -> None:
        group = ttk.LabelFrame(self, text="Tower", style="Filter.TLabelframe")
        group.grid(row=0, column=0, sticky="ew", pady=(0, SPACE_SM))
        group.columnconfigure(0, weight=1)
        ttk.Label(group, text="Name contains", underline=0).grid(row=0, column=0, sticky="w")
        self.name_entry = ttk.Entry(
            group, textvariable=self.name_var, style="Filter.TEntry", width=NAME_ENTRY_WIDTH_CHARS
        )
        self.name_entry.grid(row=1, column=0, sticky="ew", pady=(SPACE_XS, 0))
        self.name_entry.bind("<Escape>", lambda event: self.name_var.set(""))
        self.name_entry.bind("<Return>", self._submit)
        ttk.Label(group, text="Damage type").grid(row=2, column=0, sticky="w", pady=(SPACE_SM, 0))
        self.damage_type_combobox = ttk.Combobox(
            group, textvariable=self.damage_type_var, values=self._damage_types, state="readonly"
        )
        self.damage_type_combobox.grid(row=3, column=0, sticky="ew", pady=(SPACE_XS, 0))

    def _build_pop_group(self) -> None:
        group = ttk.LabelFrame(self, text="Bloon types", style="Filter.TLabelframe")
        group.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_SM))
        rows = [(name, name.capitalize()) for name in POP_PROPERTIES]
        rows.append((CAMO_ROW, "Hits camo"))
        for index, (choice_key, label) in enumerate(rows):
            ttk.Label(group, text=label).grid(row=index, column=0, sticky="w", padx=(0, SPACE_SM))
            for column, (choice, text) in enumerate(CHOICE_LABELS, start=1):
                ttk.Radiobutton(
                    group,
                    text=text,
                    value=choice,
                    variable=self.choice_vars[choice_key],
                    style="Filter.TRadiobutton",
                ).grid(row=index, column=column, sticky="w", padx=(0, SPACE_XS))

    def _build_threshold_group(self) -> None:
        group = ttk.LabelFrame(self, text="Minimum stats", style="Filter.TLabelframe")
        group.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_SM))
        group.columnconfigure(1, weight=1)
        for index, (field_name, label) in enumerate(THRESHOLD_FIELDS.items()):
            grid_row = index * 2
            ttk.Label(group, text=label).grid(
                row=grid_row, column=0, sticky="w", padx=(0, SPACE_SM)
            )
            entry = ttk.Entry(
                group,
                textvariable=self.threshold_vars[field_name],
                style="Filter.TEntry",
                width=ENTRY_WIDTH_CHARS,
                validate="key",
                validatecommand=self._number_check,
            )
            entry.grid(row=grid_row, column=1, sticky="ew")
            entry.bind("<Return>", self._submit)
            error = ttk.Label(group, text="", style="Error.TLabel")
            error.grid(row=grid_row + 1, column=0, columnspan=2, sticky="w")
            self._entries[field_name] = entry
            self._error_labels[field_name] = error

    def _build_options_group(self) -> None:
        group = ttk.LabelFrame(self, text="Results", style="Filter.TLabelframe")
        group.grid(row=3, column=0, sticky="ew", pady=(0, SPACE_SM))
        group.columnconfigure(1, weight=1)
        ttk.Label(group, text="Sort by").grid(row=0, column=0, sticky="w", padx=(0, SPACE_SM))
        self.sort_combobox = ttk.Combobox(
            group, textvariable=self.sort_var, values=("", *SORT_COLUMNS), state="readonly"
        )
        self.sort_combobox.grid(row=0, column=1, sticky="ew")
        self.sort_combobox.bind("<<ComboboxSelected>>", self._sort_chosen)
        ttk.Label(group, text="Limit").grid(row=1, column=0, sticky="w", padx=(0, SPACE_SM))
        self.limit_spinbox = ttk.Spinbox(
            group,
            textvariable=self.limit_var,
            from_=1,
            to=MAX_LIMIT,
            width=ENTRY_WIDTH_CHARS,
            validate="key",
            validatecommand=self._whole_number_check,
        )
        self.limit_spinbox.grid(row=1, column=1, sticky="ew")
        self.limit_spinbox.bind("<Return>", self._submit)
        error = ttk.Label(group, text="", style="Error.TLabel")
        error.grid(row=2, column=0, columnspan=2, sticky="w")
        self._entries["limit"] = self.limit_spinbox
        self._error_labels["limit"] = error

    def _build_buttons(self) -> None:
        button_bar = ttk.Frame(self)
        button_bar.grid(row=4, column=0, sticky="ew")
        button_bar.columnconfigure((0, 1), weight=1, uniform="buttons")
        self.reset_button = ttk.Button(
            button_bar, text="Reset", underline=0, style="Secondary.TButton", command=self._on_reset
        )
        self.search_button = ttk.Button(
            button_bar, text="Search", underline=0, style="Action.TButton", command=self._submit
        )
        self.reset_button.grid(row=0, column=0, sticky="ew", padx=(0, SPACE_SM))
        self.search_button.grid(row=0, column=1, sticky="ew")

    def _watch_variables(self) -> None:
        every_var = [
            self.name_var,
            self.damage_type_var,
            self.limit_var,
            *self.choice_vars.values(),
            *self.threshold_vars.values(),
        ]
        for variable in every_var:
            variable.trace_add("write", self._notify_change)

    def get_inputs(self) -> FilterInputs:
        return FilterInputs(
            name_text=self.name_var.get(),
            pops={name: PopChoice(self.choice_vars[name].get()) for name in POP_PROPERTIES},
            camo=PopChoice(self.choice_vars[CAMO_ROW].get()),
            damage_type=self.damage_type_var.get(),
            limit=self.limit_var.get(),
            **{name: variable.get() for name, variable in self.threshold_vars.items()},
        )

    def get_form(self) -> dict[str, str | bool]:
        inputs = self.get_inputs()
        form: dict[str, str | bool] = {
            "name": inputs.name_text,
            "camo": CAMO_FORM_VALUES[inputs.camo],
            "damage_type": inputs.damage_type,
            "sort": self.sort_var.get(),
            "limit": inputs.limit,
            **{name: str(choice) for name, choice in inputs.pops.items()},
        }
        for name in self.threshold_vars:
            form[FORM_KEYS.get(name, name)] = getattr(inputs, name)
        return form

    def set_sort(self, column: str | None) -> None:
        self.sort_var.set(column or "")

    def _sort_chosen(self, event: tk.Event | None = None) -> None:
        if self._on_sort_selected is not None:
            self._on_sort_selected(self.sort_var.get() or None)

    def set_inputs(self, inputs: FilterInputs) -> None:
        self._muted = True
        try:
            self.name_var.set(inputs.name_text)
            self.damage_type_var.set(inputs.damage_type)
            self.limit_var.set(inputs.limit)
            for name in POP_PROPERTIES:
                self.choice_vars[name].set(inputs.pops.get(name, PopChoice.ANY))
            self.choice_vars[CAMO_ROW].set(inputs.camo)
            for name, variable in self.threshold_vars.items():
                variable.set(getattr(inputs, name))
        finally:
            self._muted = False

    def set_errors(self, errors: dict[str, str]) -> None:
        for name, label in self._error_labels.items():
            message = errors.get(name, "")
            label.configure(text=message)
            self._entries[name].state(["invalid"] if message else ["!invalid"])

    def focus_name(self) -> None:
        self.name_entry.focus_set()
        self.name_entry.selection_range(0, "end")

    def _notify_change(self, *_: object) -> None:
        if not self._muted:
            self._on_change(self.get_inputs())

    def _submit(self, event: tk.Event | None = None) -> None:
        self._on_submit(self.get_inputs())
