from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from btd6.formatting import format_row
from btd6.query import POP_PROPERTIES, SORT_COLUMNS, QueryError, UpgradeFilters
from btd6.recommend import DEFAULT_HORIZON, OwnedTower, parse_owned

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


def parse_positive_int(field: str, cleaned: str) -> int:
    try:
        number = int(cleaned)
    except ValueError:
        raise QueryError(f"{field} must be a whole number, got {cleaned!r}") from None
    if number < 1:
        raise QueryError(f"{field} must be at least 1, got {number}")
    return number


def parse_limit(text: str) -> int | None:
    cleaned = text.strip()
    return parse_positive_int("limit", cleaned) if cleaned else None


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


@dataclass(frozen=True)
class RecommendOptions:
    round_number: int
    money: int
    difficulty: str
    limit: int | None
    horizon: int = DEFAULT_HORIZON
    one_per_tower: bool = False
    owned: tuple[OwnedTower, ...] = ()


def parse_required_int(field: str, value: object) -> int:
    text = str(value or "").strip()
    if not text:
        raise QueryError(f"{field} is required")
    try:
        return int(text)
    except ValueError:
        raise QueryError(f"{field} must be a whole number, got {text!r}") from None


def parse_horizon(form: Mapping[str, Any]) -> int:
    text = str(form.get("horizon") or "").strip()
    return parse_positive_int("horizon", text) if text else DEFAULT_HORIZON


def parse_one_per_tower(value: object) -> bool:
    text = str(value or "").strip()
    if text.lower() in ("", "false", "0"):
        return False
    if text.lower() in ("true", "1", "on"):
        return True
    raise QueryError(f"one_per_tower must be true or false, got {text!r}")


def parse_owned_form(value: object) -> tuple[OwnedTower, ...]:
    if value is None:
        return ()
    texts = [value] if isinstance(value, str) else list(value)
    return tuple(parse_owned(text) for text in texts)


def form_to_recommend_options(form: Mapping[str, Any]) -> RecommendOptions:
    round_number = parse_required_int("round", form.get("round"))
    money = parse_required_int("money", form.get("money"))
    if money < 0:
        raise QueryError(f"money must be 0 or more, got {money}")
    difficulty = str(form.get("difficulty") or "").strip() or "medium"
    limit = parse_limit(str(form.get("limit") or ""))
    return RecommendOptions(
        round_number,
        money,
        difficulty,
        limit,
        parse_horizon(form),
        parse_one_per_tower(form.get("one_per_tower")),
        parse_owned_form(form.get("owned")),
    )
