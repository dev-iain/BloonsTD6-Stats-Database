from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from btd6.income import RoundIncome

RESULT_COLUMNS: dict[str, str] = {
    "tower_name": "tower",
    "path": "path",
    "damage_type": "type",
    "projectile_damage": "damage",
    "projectile_pierce": "pierce",
    "range": "range",
    "projectile_speed": "speed",
    "attack_rate": "rate",
    "can_hit_camo": "camo",
    "can_pop_lead": "lead",
    "can_pop_black": "black",
    "can_pop_white": "white",
    "can_pop_purple": "purple",
    "can_pop_glass": "glass",
    "can_pop_frozen": "frozen",
}
FLAG_COLUMNS = frozenset(
    name for name in RESULT_COLUMNS if name.startswith(("can_pop_", "can_hit_"))
)
EMPTY_RESULTS_MESSAGE = "No upgrades match these filters."
POP_CODES = {
    "lead": "Ld",
    "black": "Bk",
    "white": "Wh",
    "purple": "Pu",
    "glass": "Gl",
    "frozen": "Fr",
}
TABLE_CELL_COLUMNS = (
    "tower_name",
    "path",
    "attack_rate",
    "projectile_count",
    "projectile_damage",
    "projectile_pierce",
    "projectile_speed",
)


def whole_float_to_int(value: float) -> float | int:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def format_cell(column: str, value: object) -> str:
    if value is None:
        return "-"
    if column in FLAG_COLUMNS:
        return "yes" if value else "no"
    if isinstance(value, float):
        return str(whole_float_to_int(value))
    return str(value)


def format_amount(amount: float) -> str:
    return str(whole_float_to_int(round(amount, 1)))


def format_money(amount: float) -> str:
    rounded = whole_float_to_int(round(amount, 1))
    if isinstance(rounded, int):
        return f"${rounded:,}"
    return f"${rounded:,.1f}"


def income_summary(income: RoundIncome, round_number: int) -> str:
    return (
        f"Round {round_number}: {format_money(income.pop_cash)} pop cash + "
        f"{format_money(income.end_bonus)} end bonus = {format_money(income.total)}"
    )


def pops_summary(result_row: Mapping[str, Any]) -> str:
    popped = [code for prop, code in POP_CODES.items() if result_row[f"can_pop_{prop}"]]
    if len(popped) == len(POP_CODES):
        return "All"
    return " ".join(popped) if popped else "-"


def format_row(result_row: Mapping[str, Any]) -> tuple[str, ...]:
    cells = [format_cell(column, result_row[column]) for column in TABLE_CELL_COLUMNS]
    return (*cells, pops_summary(result_row))
