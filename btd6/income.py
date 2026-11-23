from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from btd6.rounds import validate_round

SUPER_CERAMIC_CASH = 87
LAST_NORMAL_ROUND = 80
END_BONUS_BASE = 100

POP_CASH_COLUMNS = {False: "pop_cash", True: "pop_cash_super"}
ZEBRA_SUPER_CHILD = [("Black", 1)]


def surviving_children(
    name: str,
    children: dict[str, list[tuple[str, int]]],
    moab_names: frozenset[str] | set[str],
    super_ceramic: bool,
) -> list[tuple[str, int]]:
    released = children.get(name, [])
    if not super_ceramic or name in moab_names:
        return released
    if name == "Zebra":
        return ZEBRA_SUPER_CHILD
    return released[:1] and [(released[0][0], 1)]


def bloon_pop_cash(
    name: str,
    children: dict[str, list[tuple[str, int]]],
    moab_names: frozenset[str] | set[str],
    super_ceramic: bool,
) -> int:
    """Cash for fully popping one bloon: its own layer plus every released child."""
    own = SUPER_CERAMIC_CASH if super_ceramic and name == "Ceramic" else 1
    released = surviving_children(name, children, moab_names, super_ceramic)
    return own + sum(
        count * bloon_pop_cash(child, children, moab_names, super_ceramic)
        for child, count in released
    )


@dataclass(frozen=True)
class RoundIncome:
    pop_cash: float
    end_bonus: int
    total: float


def end_of_round_bonus(round_number: int) -> int:
    return END_BONUS_BASE + round_number


def pop_cash_column(round_number: int) -> str:
    return POP_CASH_COLUMNS[round_number > LAST_NORMAL_ROUND]


def round_multiplier(connection: sqlite3.Connection, round_number: int) -> float:
    if round_number < 1:
        raise ValueError(f"Round must be at least 1, got {round_number}")
    row = connection.execute(
        "SELECT multiplier FROM income_thresholds WHERE max_round >= ? ORDER BY max_round LIMIT 1",
        (round_number,),
    ).fetchone()
    if row is not None:
        return row[0]
    if connection.execute("SELECT 1 FROM income_thresholds LIMIT 1").fetchone() is None:
        raise ValueError("No income thresholds loaded")
    settings = connection.execute(
        "SELECT final_multiplier FROM income_settings WHERE id = 1"
    ).fetchone()
    if settings is None:
        raise ValueError("No income settings loaded")
    return settings[0]


def raw_pop_cash(connection: sqlite3.Connection, round_number: int) -> int:
    column = pop_cash_column(round_number)
    missing = connection.execute(
        f"SELECT bloons.name FROM round_groups JOIN bloons ON bloons.id = round_groups.bloon_id "
        f"WHERE round_groups.round = ? AND bloons.{column} IS NULL LIMIT 1",
        (round_number,),
    ).fetchone()
    if missing is not None:
        raise ValueError(f"Bloon {missing[0]} has no {column}; cannot price round {round_number}")
    total = connection.execute(
        f"SELECT SUM(round_groups.count * bloons.{column}) FROM round_groups "
        f"JOIN bloons ON bloons.id = round_groups.bloon_id WHERE round_groups.round = ?",
        (round_number,),
    ).fetchone()[0]
    return total or 0


def compute_round_income(connection: sqlite3.Connection, round_number: int) -> RoundIncome:
    pop_cash = raw_pop_cash(connection, round_number) * round_multiplier(connection, round_number)
    end_bonus = end_of_round_bonus(round_number)
    return RoundIncome(pop_cash=pop_cash, end_bonus=end_bonus, total=pop_cash + end_bonus)


def round_income(connection: sqlite3.Connection, round_number: int) -> RoundIncome:
    validate_round(connection, round_number)
    return compute_round_income(connection, round_number)


def cumulative_income(connection: sqlite3.Connection, up_to_round: int) -> float:
    validate_round(connection, up_to_round)
    return sum(
        compute_round_income(connection, round_number).total
        for round_number in range(1, up_to_round + 1)
    )
