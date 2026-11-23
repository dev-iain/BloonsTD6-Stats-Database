from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from btd6.formatting import EMPTY_RESULTS_MESSAGE
from btd6.query import POP_PROPERTIES, QueryError, UpgradeFilters
from btd6.ui.scheduler import Scheduler
from btd6.ui.search_viewmodel import MISSING_DATABASE_MESSAGE, parse_limit, parse_optional_float
from btd6.ui.worker import BackgroundRunner

DEBOUNCE_MS = 250
THRESHOLD_FIELDS = {
    "min_range": "Range",
    "min_pierce": "Pierce",
    "min_damage": "Damage",
    "min_projectile_speed": "Projectile speed",
}


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    heading: str
    width_chars: int
    numeric: bool
    sortable: bool
    hint: str = ""


TABLE_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("tower_name", "Tower", 14, False, False),
    ColumnSpec("path", "Path", 7, False, True),
    ColumnSpec(
        "attack_rate", "Attack rate (s)", 14, True, True, "Seconds between attacks: lower is faster"
    ),
    ColumnSpec("projectile_count", "Projectiles", 11, True, True),
    ColumnSpec("projectile_damage", "Damage", 8, True, True),
    ColumnSpec("projectile_pierce", "Pierce", 8, True, True),
    ColumnSpec("projectile_speed", "Speed", 8, True, True),
    ColumnSpec(
        "pops",
        "Pops",
        18,
        False,
        False,
        "Ld lead, Bk black, Wh white, Pu purple, Gl glass, Fr frozen",
    ),
)
SORTABLE_KEYS = frozenset(spec.key for spec in TABLE_COLUMNS if spec.sortable)


class PopChoice(StrEnum):
    ANY = "any"
    CAN = "can"
    CANNOT = "cannot"


def choice_to_flag(choice: PopChoice | str) -> bool | None:
    if choice == PopChoice.CAN:
        return True
    if choice == PopChoice.CANNOT:
        return False
    return None


def default_pop_choices() -> dict[str, PopChoice]:
    return {name: PopChoice.ANY for name in POP_PROPERTIES}


@dataclass(frozen=True)
class FilterInputs:
    """Raw widget text and choices; parsed and validated by `parse_filters`."""

    name_text: str = ""
    pops: Mapping[str, PopChoice] = field(default_factory=default_pop_choices)
    camo: PopChoice = PopChoice.ANY
    min_range: str = ""
    min_pierce: str = ""
    min_damage: str = ""
    min_projectile_speed: str = ""
    damage_type: str = "Any"
    limit: str = ""


class InputError(ValueError):
    pass


def parse_threshold(label: str, text: str) -> float | None:
    try:
        number = parse_optional_float(text)
    except ValueError:
        raise InputError(f"{label} must be a number") from None
    if number is not None and number < 0:
        raise InputError(f"{label} must be 0 or more")
    return number


def parse_result_limit(text: str) -> tuple[int | None, dict[str, str]]:
    try:
        return parse_limit(text), {}
    except QueryError as error:
        return None, {"limit": str(error)}


def parse_filters(inputs: FilterInputs) -> tuple[UpgradeFilters | None, dict[str, str]]:
    errors: dict[str, str] = {}
    values: dict[str, Any] = {}
    for field_name, label in THRESHOLD_FIELDS.items():
        try:
            values[field_name] = parse_threshold(label, getattr(inputs, field_name))
        except InputError as error:
            errors[field_name] = str(error)
    if errors:
        return None, errors
    for prop in POP_PROPERTIES:
        values[f"can_pop_{prop}"] = choice_to_flag(inputs.pops.get(prop, PopChoice.ANY))
    values["can_hit_camo"] = choice_to_flag(inputs.camo)
    name_text = inputs.name_text.strip()
    values["tower_name_contains"] = name_text or None
    values["damage_type"] = inputs.damage_type if inputs.damage_type not in ("", "Any") else None
    return UpgradeFilters(**values), {}


def next_sort(current: str | None, descending: bool, clicked: str) -> tuple[str | None, bool]:
    if clicked not in SORTABLE_KEYS:
        return current, descending
    if clicked == current:
        return clicked, not descending
    return clicked, False


def count_message(count: int) -> str:
    return f"{count} upgrade" + ("" if count == 1 else "s")


class SearchViewPort(Protocol):
    def show_rows(self, rows: list[tuple[str, ...]]) -> None: ...

    def show_placeholder(self, message: str, offer_load: bool) -> None: ...

    def show_status(self, message: str, is_error: bool) -> None: ...

    def set_busy(self, busy: bool) -> None: ...

    def show_field_errors(self, errors: dict[str, str]) -> None: ...

    def show_sort(self, column: str | None, descending: bool) -> None: ...

    def show_filters(self, inputs: FilterInputs) -> None: ...


class DatabaseMissingError(Exception):
    """The database file or its tables do not exist yet."""


QueryFunction = Callable[[UpgradeFilters, str | None, bool, int | None], list[tuple[str, ...]]]
LoadFunction = Callable[[Callable[[str], None]], str]


class SearchPresenter:
    def __init__(
        self,
        view: SearchViewPort,
        runner: BackgroundRunner,
        scheduler: Scheduler,
        run_query: QueryFunction,
        run_load: LoadFunction,
    ) -> None:
        self._view = view
        self._runner = runner
        self._scheduler = scheduler
        self._run_query = run_query
        self._run_load = run_load
        self._inputs = FilterInputs()
        self._sort_column: str | None = None
        self._descending = False
        self._request_id = 0
        self._debounce_token: str | None = None
        self._loading = False

    def start(self) -> None:
        self.search_now()

    def on_filters_changed(self, inputs: FilterInputs) -> None:
        self._inputs = inputs
        self._cancel_debounce()
        self._debounce_token = self._scheduler.after(DEBOUNCE_MS, self.search_now)

    def on_submit(self, inputs: FilterInputs) -> None:
        self._inputs = inputs
        self.search_now()

    def reset(self) -> None:
        self._inputs = FilterInputs()
        self._view.show_filters(self._inputs)
        self.search_now()

    def on_sort_selected(self, column: str | None) -> None:
        self._sort_column, self._descending = column, False
        self._view.show_sort(column, False)
        self.search_now()

    def on_sort(self, column: str) -> None:
        if column not in SORTABLE_KEYS:
            return
        self._sort_column, self._descending = next_sort(self._sort_column, self._descending, column)
        self._view.show_sort(self._sort_column, self._descending)
        self.search_now()

    def close(self) -> None:
        self._cancel_debounce()
        self._request_id += 1

    def _cancel_debounce(self) -> None:
        if self._debounce_token is not None:
            self._scheduler.after_cancel(self._debounce_token)
            self._debounce_token = None

    def search_now(self) -> None:
        self._cancel_debounce()
        filters, limit, errors = self._parse_request()
        self._view.show_field_errors(errors)
        self._request_id += 1
        if filters is None or errors:
            self._view.set_busy(False)
            self._view.show_status("Fix the highlighted filters to search", True)
            return
        request_id = self._request_id
        self._view.set_busy(True)
        self._view.show_status("Searching...", False)
        sort_column, descending = self._sort_column, self._descending
        self._runner.submit(
            lambda report: self._run_query(filters, sort_column, descending, limit),
            lambda rows: self._on_rows(request_id, rows),
            lambda error: self._on_query_error(request_id, error),
        )

    def _parse_request(self) -> tuple[UpgradeFilters | None, int | None, dict[str, str]]:
        filters, errors = parse_filters(self._inputs)
        limit, limit_errors = parse_result_limit(self._inputs.limit)
        return filters, limit, {**errors, **limit_errors}

    def _on_rows(self, request_id: int, rows: list[tuple[str, ...]]) -> None:
        if request_id != self._request_id:
            return
        self._view.set_busy(False)
        self._view.show_rows(rows)
        if rows:
            self._view.show_status(count_message(len(rows)), False)
        else:
            self._view.show_placeholder(EMPTY_RESULTS_MESSAGE, False)
            self._view.show_status(EMPTY_RESULTS_MESSAGE, False)

    def _on_query_error(self, request_id: int, error: Exception) -> None:
        if request_id != self._request_id:
            return
        self._view.set_busy(False)
        if isinstance(error, DatabaseMissingError):
            self._view.show_placeholder(MISSING_DATABASE_MESSAGE, True)
            self._view.show_status("Database not loaded", False)
        elif isinstance(error, QueryError):
            self._view.show_status(f"Search failed: {error}", True)
        else:
            self._view.show_status("Search failed: the database could not be read", True)

    def load_database(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._view.set_busy(True)
        self._view.show_status("Loading tower data...", False)
        self._runner.submit(
            self._run_load,
            self._on_load_done,
            self._on_load_error,
            on_progress=lambda text: self._view.show_status(text, False),
        )

    def _on_load_done(self, summary: str) -> None:
        self._loading = False
        self._view.show_status(summary, False)
        self.search_now()

    def _on_load_error(self, error: Exception) -> None:
        self._loading = False
        self._view.set_busy(False)
        self._view.show_status(f"Load failed: {error}", True)
