from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from btd6.formatting import format_row
from btd6.query import POP_PROPERTIES, SORT_COLUMNS, QueryError, UpgradeFilters

ANY_DAMAGE_TYPE = "Any"
POP_CHOICES: dict[str, bool | None] = {"any": None, "can": True, "cannot": False}
CAMO_CHOICES: dict[str, bool | None] = {"either": None, "yes": True, "no": False}
NUMERIC_FIELDS = {
    "min_range": "min_range",
    "min_pierce": "min_pierce",
    "min_damage": "min_damage",
    "min_speed": "min_projectile_speed",
}


def parse_optional_float(text: str) -> float | None:
    """Blank gives None; text that is not a finite number raises ValueError."""
    cleaned = text.strip()
    if not cleaned:
        return None
    number = float(cleaned)
    if not math.isfinite(number):
        raise ValueError(cleaned)
    return number


def parse_limit(text: str) -> int | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        limit = int(cleaned)
    except ValueError:
        raise QueryError(f"limit must be a whole number, got {cleaned!r}") from None
    if limit < 1:
        raise QueryError(f"limit must be at least 1, got {limit}")
    return limit


def parse_minimum(field: str, text: str) -> float | None:
    try:
        number = parse_optional_float(text)
    except ValueError:
        raise QueryError(f"{field} must be a number, got {text.strip()!r}") from None
    if number is not None and number < 0:
        raise QueryError(f"{field} must be 0 or more, got {number}")
    return number


def describe_choices(options: Sequence[str]) -> str:
    return f"{', '.join(options[:-1])} or {options[-1]}"


def choice_to_flag(field: str, value: object, choices: Mapping[str, bool | None]) -> bool | None:
    if isinstance(value, bool):
        return True if value else None
    if value not in choices:
        raise QueryError(f'{field} must be {describe_choices(list(choices))}, got "{value}"')
    return choices[str(value)]


def form_to_filters(form: Mapping[str, Any]) -> UpgradeFilters:
    values: dict[str, Any] = {
        f"can_pop_{prop}": choice_to_flag(prop, form.get(prop, "any"), POP_CHOICES)
        for prop in POP_PROPERTIES
    }
    for form_key, field in NUMERIC_FIELDS.items():
        values[field] = parse_minimum(form_key, str(form.get(form_key, "")))
    values["can_hit_camo"] = choice_to_flag("camo", form.get("camo", "either"), CAMO_CHOICES)
    values["tower_name_contains"] = str(form.get("name", "")).strip() or None
    damage_type = str(form.get("damage_type", "")).strip()
    values["damage_type"] = None if damage_type in ("", ANY_DAMAGE_TYPE) else damage_type
    return UpgradeFilters(**values)


def form_to_search_options(form: Mapping[str, Any]) -> tuple[str | None, int | None]:
    sort_column = str(form.get("sort", "")).strip() or None
    if sort_column is not None and sort_column not in SORT_COLUMNS:
        allowed = ", ".join(SORT_COLUMNS)
        raise QueryError(f'Cannot sort by "{sort_column}". Allowed: {allowed}')
    return sort_column, parse_limit(str(form.get("limit", "")))


def rows_to_cells(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, ...]]:
    return [format_row(result_row) for result_row in rows]
