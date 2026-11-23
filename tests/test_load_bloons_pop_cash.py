from __future__ import annotations

import sqlite3

import pytest

from btd6.db.connection import connect
from btd6.db.round_loader import load_bloons
from btd6.db.seed import initialize_database
from tests.test_round_loader import BLOON_ROWS


@pytest.fixture
def connection() -> sqlite3.Connection:
    conn = connect(":memory:")
    initialize_database(conn)
    return conn


def stored(conn: sqlite3.Connection) -> dict[str, tuple]:
    rows = conn.execute("SELECT name, pop_cash, pop_cash_super FROM bloons")
    return {row["name"]: (row["pop_cash"], row["pop_cash_super"]) for row in rows}


def test_load_bloons_stores_pop_cash(connection) -> None:
    rows = [
        {**BLOON_ROWS[0], "pop_cash": 1, "pop_cash_super": 1},
        {**BLOON_ROWS[2], "pop_cash": 381, "pop_cash_super": 380},
    ]
    load_bloons(connection, rows)
    assert stored(connection) == {"Red": (1, 1), "Moab": (381, 380)}


def test_load_bloons_updates_pop_cash_on_reload(connection) -> None:
    load_bloons(connection, [{**BLOON_ROWS[0], "pop_cash": 5, "pop_cash_super": 5}])
    load_bloons(connection, [{**BLOON_ROWS[0], "pop_cash": 1, "pop_cash_super": 1}])
    assert stored(connection) == {"Red": (1, 1)}


def test_load_bloons_without_pop_cash_keys_stores_null(connection) -> None:
    load_bloons(connection, BLOON_ROWS)
    assert stored(connection)["Red"] == (None, None)


def test_load_bloons_negative_pop_cash_rolls_back(connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        load_bloons(connection, [{**BLOON_ROWS[0], "pop_cash": -1, "pop_cash_super": 1}])
    assert stored(connection) == {}
