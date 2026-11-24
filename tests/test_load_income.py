from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from btd6.db.connection import connect
from btd6.db.round_loader import load_income
from btd6.db.seed import initialize_database
from tests.factories import IncomeSetFactory

CHANGED = IncomeSetFactory(items=[{"threshold": 50, "multiplier": 0.9}], finalMultiplier=0.03)


@pytest.fixture
def connection() -> sqlite3.Connection:
    conn = connect(":memory:")
    initialize_database(conn)
    return conn


def snapshot(conn: sqlite3.Connection) -> tuple[list[tuple], list[tuple]]:
    thresholds = conn.execute(
        "SELECT max_round, multiplier FROM income_thresholds ORDER BY max_round"
    ).fetchall()
    final = conn.execute("SELECT id, final_multiplier FROM income_settings").fetchall()
    return [tuple(row) for row in thresholds], [tuple(row) for row in final]


def test_load_income_first_load(connection) -> None:
    assert load_income(connection, IncomeSetFactory()) == 6
    thresholds, final = snapshot(connection)
    assert len(thresholds) == 6
    assert thresholds[0] == (50, 1)
    assert thresholds[-1] == (140, 0.04)
    assert final == [(1, 0.02)]


def test_load_income_reload_no_duplicates(connection) -> None:
    load_income(connection, IncomeSetFactory())
    first = snapshot(connection)
    assert load_income(connection, IncomeSetFactory()) == 6
    assert snapshot(connection) == first


def test_load_income_changed_values_overwrite(connection) -> None:
    load_income(connection, IncomeSetFactory())
    assert load_income(connection, CHANGED) == 1
    assert snapshot(connection) == ([(50, 0.9)], [(1, 0.03)])


def test_load_income_empty_thresholds(connection) -> None:
    assert load_income(connection, IncomeSetFactory(items=[])) == 0
    assert snapshot(connection) == ([], [(1, 0.02)])


def test_load_income_invalid_rolls_back_and_keeps_old(connection) -> None:
    load_income(connection, IncomeSetFactory())
    before = snapshot(connection)
    bad = IncomeSetFactory(items=[{"threshold": 0, "multiplier": 1}])
    with pytest.raises(sqlite3.IntegrityError):
        load_income(connection, bad)
    assert snapshot(connection) == before


def test_load_income_negative_final_rolls_back(connection) -> None:
    load_income(connection, IncomeSetFactory())
    before = snapshot(connection)
    with pytest.raises(sqlite3.IntegrityError):
        load_income(connection, IncomeSetFactory(finalMultiplier=-1))
    assert snapshot(connection) == before


def build_income_set(limits: list[int], final: float) -> dict[str, Any]:
    items = [
        {"threshold": limit, "multiplier": 1 / (index + 1)} for index, limit in enumerate(limits)
    ]
    return IncomeSetFactory(items=items, finalMultiplier=final)


income_sets = st.builds(
    build_income_set,
    st.lists(st.integers(1, 200), unique=True, max_size=8),
    st.sampled_from([0.0, 0.02, 0.5]),
)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=30)
@given(income_set=income_sets, repeats=st.integers(1, 3))
def test_load_income_idempotent_property(connection, income_set, repeats) -> None:
    load_income(connection, income_set)
    once = snapshot(connection)
    for _ in range(repeats - 1):
        load_income(connection, income_set)
    assert snapshot(connection) == once
