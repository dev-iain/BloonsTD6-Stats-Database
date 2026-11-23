from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from btd6.rounds import validate_round

LAST_NORMAL_ROUND = 80
END_BONUS_BASE = 100

NORMAL_POP_CASH_SQL = (
    "SELECT SUM(round_groups.count * bloons.pop_cash), "
    "MIN(CASE WHEN bloons.pop_cash IS NULL THEN bloons.name END) "
    "FROM round_groups JOIN bloons ON bloons.id = round_groups.bloon_id "
    "WHERE round_groups.round = ?"
)
SUPER_POP_CASH_SQL = (
    "SELECT SUM(round_groups.count * bloons.pop_cash_super), "
    "MIN(CASE WHEN bloons.pop_cash_super IS NULL THEN bloons.name END) "
    "FROM round_groups JOIN bloons ON bloons.id = round_groups.bloon_id "
    "WHERE round_groups.round = ?"
)


class NoIncomeDataError(ValueError):
    """Raised when income thresholds or settings are not loaded."""


@dataclass(frozen=True)
class RoundIncome:
    pop_cash: float
    end_bonus: int
    total: float


def end_of_round_bonus(round_number: int) -> int:
    return END_BONUS_BASE + round_number


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
        raise NoIncomeDataError("No income thresholds loaded")
    settings = connection.execute(
        "SELECT final_multiplier FROM income_settings WHERE id = 1"
    ).fetchone()
    if settings is None:
        raise NoIncomeDataError("No income settings loaded")
    return settings[0]


def raw_pop_cash(connection: sqlite3.Connection, round_number: int) -> int:
    if round_number > LAST_NORMAL_ROUND:
        query, column = SUPER_POP_CASH_SQL, "pop_cash_super"
    else:
        query, column = NORMAL_POP_CASH_SQL, "pop_cash"
    total, missing_name = connection.execute(query, (round_number,)).fetchone()
    if missing_name is not None:
        raise ValueError(f"Bloon {missing_name} has no {column}; cannot price round {round_number}")
    return total or 0


def compute_round_income(connection: sqlite3.Connection, round_number: int) -> RoundIncome:
    pop_cash = raw_pop_cash(connection, round_number) * round_multiplier(connection, round_number)
    end_bonus = end_of_round_bonus(round_number)
    return RoundIncome(pop_cash=pop_cash, end_bonus=end_bonus, total=pop_cash + end_bonus)


def round_income(connection: sqlite3.Connection, round_number: int) -> RoundIncome:
    validate_round(connection, round_number)
    return compute_round_income(connection, round_number)


def round_incomes(connection: sqlite3.Connection, up_to_round: int) -> list[RoundIncome]:
    validate_round(connection, up_to_round)
    return [
        compute_round_income(connection, round_number) for round_number in range(1, up_to_round + 1)
    ]


def cumulative_income(connection: sqlite3.Connection, up_to_round: int) -> float:
    return sum(income.total for income in round_incomes(connection, up_to_round))
