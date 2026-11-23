from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from btd6.db import apply_migrations, connect
from btd6.db.round_loader import load_bloons, load_income, load_rounds
from btd6.income import RoundIncome, cumulative_income, round_income, round_multiplier

FIXTURES = Path(__file__).parent / "fixtures"
SHORT_ROUNDS = 5
LAST_ROUND = 100
ALLOWED_MULTIPLIERS = (1, 0.5, 0.2, 0.1, 0.05, 0.04, 0.02)
SHARED_DB = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])


def read_wiki_rows() -> list[dict[str, float]]:
    with (FIXTURES / "wiki_round_cash.csv").open(newline="") as handle:
        return [{key: float(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def read_group_rows(max_round: int) -> list[dict[str, Any]]:
    with (FIXTURES / "roundset_rows_1_100.csv").open(newline="") as handle:
        rows = [
            {
                "round": int(row["round"]),
                "group_index": int(row["group_index"]),
                "bloon": row["bloon"],
                "count": int(row["count"]),
                "start": float(row["start"]),
                "duration": float(row["duration"]),
            }
            for row in csv.DictReader(handle)
        ]
    return [row for row in rows if row["round"] <= max_round]


def build_connection(max_round: int | None, with_income: bool = True) -> sqlite3.Connection:
    connection = connect(":memory:")
    apply_migrations(connection)
    load_bloons(connection, json.loads((FIXTURES / "bloon_rows.json").read_text()))
    if with_income:
        load_income(connection, json.loads((FIXTURES / "default_income_set.json").read_text()))
    if max_round is not None:
        bloon_ids = {
            row["name"]: row["id"] for row in connection.execute("SELECT id, name FROM bloons")
        }
        load_rounds(connection, read_group_rows(max_round), bloon_ids)
    return connection


@pytest.fixture(scope="module")
def income_db() -> sqlite3.Connection:
    return build_connection(LAST_ROUND)


@pytest.fixture(scope="module")
def short_income_db() -> sqlite3.Connection:
    return build_connection(SHORT_ROUNDS)


@pytest.fixture
def no_round_db() -> sqlite3.Connection:
    return build_connection(None)


@pytest.fixture
def no_income_db() -> sqlite3.Connection:
    return build_connection(SHORT_ROUNDS, with_income=False)


def test_round_multiplier_base(income_db) -> None:
    assert round_multiplier(income_db, 1) == pytest.approx(1.0)


@pytest.mark.parametrize("round_number", [0, -1])
def test_round_multiplier_invalid_round(income_db, round_number) -> None:
    with pytest.raises(ValueError):
        round_multiplier(income_db, round_number)


@pytest.mark.parametrize(
    ("round_number", "expected"),
    [
        (50, 1.0),
        (51, 0.5),
        (60, 0.5),
        (61, 0.2),
        (85, 0.2),
        (86, 0.1),
        (100, 0.1),
        (101, 0.05),
        (120, 0.05),
        (121, 0.04),
        (140, 0.04),
        (141, 0.02),
    ],
)
def test_round_multiplier_boundaries(income_db, round_number, expected) -> None:
    assert round_multiplier(income_db, round_number) == pytest.approx(expected)


def test_round_multiplier_no_thresholds(no_income_db) -> None:
    with pytest.raises(ValueError):
        round_multiplier(no_income_db, 1)


def test_round_multiplier_needs_no_round_data(no_round_db) -> None:
    assert round_multiplier(no_round_db, 61) == pytest.approx(0.2)


def test_round_multiplier_missing_settings_above_thresholds() -> None:
    connection = build_connection(None)
    connection.execute("DELETE FROM income_settings")
    with pytest.raises(ValueError):
        round_multiplier(connection, 141)


@SHARED_DB
@given(round_number=st.integers(min_value=1, max_value=500))
def test_round_multiplier_non_increasing_and_known(income_db, round_number) -> None:
    value = round_multiplier(income_db, round_number)
    assert any(value == pytest.approx(allowed) for allowed in ALLOWED_MULTIPLIERS)
    assert round_multiplier(income_db, round_number + 1) <= value


def test_round_income_base(income_db) -> None:
    result = round_income(income_db, 1)
    assert result.end_bonus == 101
    assert result.pop_cash == pytest.approx(20.0)
    assert result.total == pytest.approx(121.0)


@pytest.mark.parametrize(
    ("round_number", "pop_cash", "end_bonus", "total"),
    [
        (40, 381.0, 140, 521.0),
        (63, 2663.0, 163, 2826.0),
        (80, 1220.2, 180, 1400.2),
    ],
)
def test_round_income_known_rounds(income_db, round_number, pop_cash, end_bonus, total) -> None:
    result = round_income(income_db, round_number)
    assert isinstance(result, RoundIncome)
    assert result.pop_cash == pytest.approx(pop_cash)
    assert result.end_bonus == end_bonus
    assert result.total == pytest.approx(total)


def test_round_income_super_ceramic_switch(income_db) -> None:
    result = round_income(income_db, 81)
    assert result.pop_cash == pytest.approx(5185.0)
    assert result.end_bonus == 181
    assert result.total == pytest.approx(5366.0)


def test_round_income_last_round(income_db) -> None:
    result = round_income(income_db, 100)
    assert result.pop_cash == pytest.approx(1334.6)
    assert result.end_bonus == 200
    assert result.total == pytest.approx(1534.6)


@pytest.mark.parametrize("round_number", [101, 0, -1])
def test_round_income_invalid_round(income_db, round_number) -> None:
    with pytest.raises(ValueError):
        round_income(income_db, round_number)


def test_round_income_no_round_data(no_round_db) -> None:
    with pytest.raises(ValueError):
        round_income(no_round_db, 1)


@pytest.mark.parametrize(
    ("round_number", "total"), [(2, 137.0), (3, 138.0), (4, 175.0), (5, 164.0)]
)
def test_round_income_early_rounds(income_db, round_number, total) -> None:
    assert round_income(income_db, round_number).total == pytest.approx(total)


def test_round_income_short_database_bounds(short_income_db) -> None:
    assert round_income(short_income_db, 5).total == pytest.approx(164.0)
    with pytest.raises(ValueError):
        round_income(short_income_db, 6)


@pytest.mark.parametrize("wiki_row", read_wiki_rows(), ids=lambda row: f"round{int(row['round'])}")
def test_round_income_matches_wiki_csv(income_db, wiki_row) -> None:
    result = round_income(income_db, int(wiki_row["round"]))
    assert result.pop_cash == pytest.approx(wiki_row["pop_cash"])
    assert result.end_bonus == wiki_row["end_bonus"]


@pytest.mark.parametrize("column", ["pop_cash", "pop_cash_super"])
def test_round_income_null_pop_cash_raises(column) -> None:
    connection = build_connection(SHORT_ROUNDS)
    connection.execute(f"UPDATE bloons SET {column} = NULL WHERE name = 'Red'")
    with pytest.raises(ValueError):
        round_income(connection, 1 if column == "pop_cash" else 81)


def test_round_income_null_pop_cash_super_ignored_before_round_81() -> None:
    connection = build_connection(SHORT_ROUNDS)
    connection.execute("UPDATE bloons SET pop_cash_super = NULL")
    assert round_income(connection, 1).total == pytest.approx(121.0)


def test_round_income_null_on_unused_bloon_is_fine() -> None:
    connection = build_connection(SHORT_ROUNDS)
    updated = connection.execute("UPDATE bloons SET pop_cash = NULL WHERE name = 'Ceramic'")
    assert updated.rowcount == 1
    assert round_income(connection, 1).total == pytest.approx(121.0)


@SHARED_DB
@given(round_number=st.integers(min_value=1, max_value=LAST_ROUND))
def test_round_income_properties(income_db, round_number) -> None:
    result = round_income(income_db, round_number)
    assert result.end_bonus == 100 + round_number
    assert result.total == pytest.approx(result.pop_cash + result.end_bonus)
    assert result.pop_cash >= 0


def test_cumulative_income_base(income_db) -> None:
    assert cumulative_income(income_db, 5) == pytest.approx(735.0)


@pytest.mark.parametrize(("up_to", "expected"), [(1, 121.0), (5, 735.0), (40, 16856.0)])
def test_cumulative_income_known_rounds(income_db, up_to, expected) -> None:
    assert cumulative_income(income_db, up_to) == pytest.approx(expected)


def test_cumulative_income_last_round(income_db) -> None:
    assert cumulative_income(income_db, 100) == pytest.approx(178994.4)


@pytest.mark.parametrize("up_to", [101, 0, -1])
def test_cumulative_income_invalid_round(income_db, up_to) -> None:
    with pytest.raises(ValueError):
        cumulative_income(income_db, up_to)


def test_cumulative_income_no_round_data(no_round_db) -> None:
    with pytest.raises(ValueError):
        cumulative_income(no_round_db, 5)


def test_cumulative_income_short_database(short_income_db) -> None:
    assert cumulative_income(short_income_db, 5) == pytest.approx(735.0)
    with pytest.raises(ValueError):
        cumulative_income(short_income_db, 6)


@SHARED_DB
@given(up_to=st.integers(min_value=1, max_value=LAST_ROUND))
def test_cumulative_income_properties(income_db, up_to) -> None:
    total = cumulative_income(income_db, up_to)
    expected = sum(round_income(income_db, k).total for k in range(1, up_to + 1))
    assert total == pytest.approx(expected)
    assert total >= 0
    if up_to > 1:
        assert total > cumulative_income(income_db, up_to - 1)
