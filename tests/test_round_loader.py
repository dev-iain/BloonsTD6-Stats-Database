from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from btd6.db.connection import connect
from btd6.db.round_loader import load_bloons, load_rounds
from btd6.db.seed import initialize_database
from btd6.etl.extract import split_bloon_name

FIXTURES = Path(__file__).parent / "fixtures"


def bloon(name: str, health: Any, layers: int, rbe: int, is_moab: Any, speed: Any) -> dict:
    return {
        "name": name,
        "health": health,
        "health_fort": None,
        "layers": layers,
        "rbe": rbe,
        "rbe_fort": None,
        "is_moab": is_moab,
        "speed": speed,
    }


def make_red() -> dict[str, Any]:
    return bloon("Red", 1, 1, 1, False, 1.0)


BLOON_ROWS = [
    make_red(),
    bloon("Blue", 1, 2, 2, False, 1.0),
    bloon("Moab", 200, 0, 616, True, 1.0),
]


def group(round_number: int, index: int, name: str, count: int = 20) -> dict[str, Any]:
    return {
        "round": round_number,
        "group_index": index,
        "bloon": name,
        "count": count,
        "start": 0.0,
        "duration": 17.5,
    }


ROUND_ROWS = [
    group(1, 0, "Red", 20),
    group(2, 0, "Red", 35),
    group(3, 0, "Red", 5),
    group(3, 1, "BlueCamo", 3),
    group(3, 2, "Red", 2),
]


@pytest.fixture
def connection() -> sqlite3.Connection:
    conn = connect(":memory:")
    initialize_database(conn)
    return conn


def bloon_ids(conn: sqlite3.Connection) -> dict[str, int]:
    return {row[0]: row[1] for row in conn.execute("SELECT name, id FROM bloons")}


def count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def snapshot_groups(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [
        tuple(r) for r in conn.execute("SELECT * FROM round_groups ORDER BY round, group_index")
    ]


@pytest.fixture
def loaded_bloons(connection: sqlite3.Connection) -> dict[str, int]:
    load_bloons(connection, BLOON_ROWS)
    return bloon_ids(connection)


def test_load_bloons_base(connection):
    assert load_bloons(connection, BLOON_ROWS) == 3
    assert count(connection, "bloons") == 3
    flags = dict(connection.execute("SELECT name, is_moab FROM bloons").fetchall())
    assert flags["Moab"] == 1
    assert flags["Red"] == 0


def test_load_bloons_empty(connection):
    assert load_bloons(connection, []) == 0
    assert count(connection, "bloons") == 0


def test_load_bloons_single(connection):
    assert load_bloons(connection, [make_red()]) == 1
    assert list(bloon_ids(connection)) == ["Red"]


def test_load_bloons_idempotent_keeps_ids(connection):
    load_bloons(connection, BLOON_ROWS)
    before = bloon_ids(connection)
    assert load_bloons(connection, BLOON_ROWS) == 3
    assert bloon_ids(connection) == before


def test_load_bloons_updates_changed_values(connection):
    load_bloons(connection, [{**make_red(), "rbe": 99}])
    red_id = bloon_ids(connection)["Red"]
    load_bloons(connection, BLOON_ROWS)
    row = connection.execute("SELECT id, rbe FROM bloons WHERE name = 'Red'").fetchone()
    assert (row["id"], row["rbe"]) == (red_id, 1)
    assert count(connection, "bloons") == 3


def test_load_bloons_removes_unreferenced_bloon(connection):
    load_bloons(connection, [*BLOON_ROWS, bloon("Zomg", 4000, 0, 4000, True, 1.0)])
    load_bloons(connection, BLOON_ROWS)
    assert "Zomg" not in bloon_ids(connection)
    assert count(connection, "bloons") == 3


def test_load_bloons_keeps_referenced_bloon_on_failure(connection):
    load_bloons(connection, [*BLOON_ROWS, bloon("Zomg", 4000, 0, 4000, True, 1.0)])
    ids = bloon_ids(connection)
    load_rounds(connection, [group(1, 0, "Zomg", 1)], ids)
    with pytest.raises(sqlite3.IntegrityError):
        load_bloons(connection, [{**row, "rbe": 5} for row in BLOON_ROWS])
    assert bloon_ids(connection) == ids
    assert connection.execute("SELECT rbe FROM bloons WHERE name = 'Red'").fetchone()[0] == 1


def test_load_bloons_null_stats(connection):
    rows = [{**make_red(), "health": None, "speed": None}, *BLOON_ROWS[1:]]
    assert load_bloons(connection, rows) == 3
    row = connection.execute("SELECT health, speed FROM bloons WHERE name = 'Red'").fetchone()
    assert (row["health"], row["speed"]) == (None, None)


def test_load_bloons_invalid_is_moab_rolls_back(connection):
    rows = [BLOON_ROWS[1], BLOON_ROWS[2], {**make_red(), "is_moab": 2}]
    with pytest.raises(sqlite3.IntegrityError):
        load_bloons(connection, rows)
    assert count(connection, "bloons") == 0


def test_load_bloons_failure_leaves_previous_rows(connection):
    load_bloons(connection, BLOON_ROWS)
    before = bloon_ids(connection)
    with pytest.raises(sqlite3.IntegrityError):
        load_bloons(connection, [{**make_red(), "is_moab": 2}])
    assert bloon_ids(connection) == before


name_strategy = st.text(alphabet="abcdefghij", min_size=1, max_size=6)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=30)
@given(names=st.lists(name_strategy, unique=True, max_size=6))
def test_load_bloons_reload_is_idempotent(connection, names):
    rows = [bloon(name, 1, 1, 1, False, 1.0) for name in names]
    load_bloons(connection, rows)
    first = bloon_ids(connection)
    load_bloons(connection, rows)
    assert bloon_ids(connection) == first
    assert set(first) == set(names)


def test_load_bloons_parameterized_sql(connection):
    evil = "Red'; DROP TABLE bloons;--"
    load_bloons(connection, [{**make_red(), "name": evil}])
    assert list(bloon_ids(connection)) == [evil]


def test_load_rounds_base(connection, loaded_bloons):
    assert load_rounds(connection, ROUND_ROWS, loaded_bloons) == 5
    rounds = [r[0] for r in connection.execute("SELECT round FROM rounds ORDER BY round")]
    assert rounds == [1, 2, 3]
    assert count(connection, "round_groups") == 5
    first = connection.execute(
        "SELECT bloon_id, count, is_camo FROM round_groups WHERE round = 1 AND group_index = 0"
    ).fetchone()
    assert (first["bloon_id"], first["count"], first["is_camo"]) == (loaded_bloons["Red"], 20, 0)


def test_load_rounds_empty(connection, loaded_bloons):
    assert load_rounds(connection, [], loaded_bloons) == 0
    assert count(connection, "rounds") == 0
    assert count(connection, "round_groups") == 0


def test_load_rounds_full_roundset(connection, loaded_bloons):
    rows = [group(number, 0, "Red") for number in range(1, 101)]
    assert load_rounds(connection, rows, loaded_bloons) == 100
    assert count(connection, "rounds") == 100
    assert connection.execute("SELECT MAX(round) FROM rounds").fetchone()[0] == 100


def test_load_rounds_idempotent(connection, loaded_bloons):
    load_rounds(connection, ROUND_ROWS, loaded_bloons)
    before = snapshot_groups(connection)
    assert load_rounds(connection, ROUND_ROWS, loaded_bloons) == 5
    assert count(connection, "rounds") == 3
    assert [r[1:] for r in snapshot_groups(connection)] == [r[1:] for r in before]


def test_load_rounds_shorter_roundset_removes_old_rows(connection, loaded_bloons):
    load_rounds(connection, [group(n, 0, "Red") for n in range(1, 6)], loaded_bloons)
    assert load_rounds(connection, ROUND_ROWS, loaded_bloons) == 5
    rounds = [r[0] for r in connection.execute("SELECT round FROM rounds ORDER BY round")]
    assert rounds == [1, 2, 3]
    assert count(connection, "round_groups") == 5


def test_load_rounds_modifier_flags(connection, loaded_bloons):
    load_rounds(connection, ROUND_ROWS, loaded_bloons)
    row = connection.execute(
        "SELECT * FROM round_groups WHERE round = 3 AND group_index = 1"
    ).fetchone()
    assert row["bloon_id"] == loaded_bloons["Blue"]
    assert (row["is_camo"], row["is_regrow"], row["is_fortified"]) == (1, 0, 0)


def test_load_rounds_replaces_changed_groups(connection, loaded_bloons):
    load_rounds(connection, [group(1, 0, "Blue", 1)], loaded_bloons)
    load_rounds(connection, ROUND_ROWS, loaded_bloons)
    rows = connection.execute("SELECT bloon_id, count FROM round_groups WHERE round = 1").fetchall()
    assert [(r["bloon_id"], r["count"]) for r in rows] == [(loaded_bloons["Red"], 20)]
    assert count(connection, "round_groups") == 5


def assert_tables_empty(connection: sqlite3.Connection) -> None:
    assert count(connection, "rounds") == 0
    assert count(connection, "round_groups") == 0


def test_load_rounds_unknown_bloon_rolls_back(connection, loaded_bloons):
    rows = [*ROUND_ROWS[:3], group(3, 1, "Zomg", 1)]
    with pytest.raises(ValueError, match='Unknown bloon "Zomg" in round 3'):
        load_rounds(connection, rows, loaded_bloons)
    assert_tables_empty(connection)


def test_load_rounds_accepts_negative_start(connection, loaded_bloons):
    row = {**group(86, 0, "Red", 5), "start": -0.15}
    assert load_rounds(connection, [row], loaded_bloons) == 1
    stored = connection.execute("SELECT start FROM round_groups").fetchone()[0]
    assert stored == -0.15


def test_load_rounds_zero_count_rolls_back(connection, loaded_bloons):
    with pytest.raises(sqlite3.IntegrityError):
        load_rounds(connection, [group(1, 0, "Red", 0)], loaded_bloons)
    assert_tables_empty(connection)


def test_load_rounds_negative_count_rolls_back(connection, loaded_bloons):
    with pytest.raises(sqlite3.IntegrityError):
        load_rounds(connection, [group(1, 0, "Red", -1)], loaded_bloons)
    assert_tables_empty(connection)


def test_load_rounds_duplicate_group_rolls_back(connection, loaded_bloons):
    with pytest.raises(sqlite3.IntegrityError):
        load_rounds(connection, [group(1, 0, "Red"), group(1, 0, "Red")], loaded_bloons)
    assert_tables_empty(connection)


def test_load_rounds_round_zero_rolls_back(connection, loaded_bloons):
    with pytest.raises(sqlite3.IntegrityError):
        load_rounds(connection, [group(0, 0, "Red")], loaded_bloons)
    assert_tables_empty(connection)


@pytest.mark.parametrize(
    ("bad_rows", "error"),
    [
        ([*ROUND_ROWS[:2], group(3, 0, "Zomg")], ValueError),
        ([*ROUND_ROWS[:2], group(3, 0, "Red", 0)], sqlite3.IntegrityError),
    ],
)
def test_load_rounds_failure_leaves_old_rows(connection, loaded_bloons, bad_rows, error):
    load_rounds(connection, ROUND_ROWS, loaded_bloons)
    before = snapshot_groups(connection)
    with pytest.raises(error):
        load_rounds(connection, bad_rows, loaded_bloons)
    assert count(connection, "rounds") == 3
    assert snapshot_groups(connection) == before


def test_load_rounds_bloon_id_must_exist(connection):
    with pytest.raises(sqlite3.IntegrityError):
        load_rounds(connection, [group(1, 0, "Red")], {"Red": 9999})
    assert_tables_empty(connection)


def test_load_rounds_keeps_group_order(connection, loaded_bloons):
    load_rounds(connection, ROUND_ROWS, loaded_bloons)
    names = [
        row[0]
        for row in connection.execute(
            "SELECT bloons.name FROM round_groups JOIN bloons ON bloons.id = bloon_id "
            "WHERE round = 3 ORDER BY group_index"
        )
    ]
    assert names == ["Red", "Blue", "Red"]


def read_back_names(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    query = (
        "SELECT round, group_index, bloons.name AS base, is_camo, is_regrow, is_fortified, "
        "count, start, duration FROM round_groups JOIN bloons ON bloons.id = bloon_id "
        "ORDER BY round, group_index"
    )
    rows = []
    for row in connection.execute(query):
        name = row["base"]
        name += "Fortified" * row["is_fortified"] + "Camo" * row["is_camo"]
        name += "Regrow" * row["is_regrow"]
        rows.append(
            {
                "round": row["round"],
                "group_index": row["group_index"],
                "bloon": name,
                "count": row["count"],
                "start": row["start"],
                "duration": row["duration"],
            }
        )
    return rows


def test_load_rounds_round_trip_fixture(connection):
    with open(FIXTURES / "default_roundset_first10_rows.csv", newline="") as handle:
        expected = [
            {
                "round": int(r["round"]),
                "group_index": int(r["group_index"]),
                "bloon": r["bloon"],
                "count": int(r["count"]),
                "start": float(r["start"]),
                "duration": float(r["duration"]),
            }
            for r in csv.DictReader(handle)
        ]
    base_names = sorted({split_bloon_name(row["bloon"])[0] for row in expected})
    load_bloons(connection, [bloon(name, 1, 1, 1, False, 1.0) for name in base_names])
    load_rounds(connection, expected, bloon_ids(connection))
    assert read_back_names(connection) == expected


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=30)
@given(counts=st.lists(st.integers(min_value=1, max_value=50), max_size=8))
def test_load_rounds_reload_is_idempotent(connection, counts):
    load_bloons(connection, BLOON_ROWS)
    ids = bloon_ids(connection)
    rows = [group(index + 1, 0, "Red", number) for index, number in enumerate(counts)]
    load_rounds(connection, rows, ids)
    assert load_rounds(connection, rows, ids) == len(rows)
    assert count(connection, "round_groups") == len(rows)
    assert count(connection, "rounds") == len(rows)
