from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path

import pytest

from btd6.db import apply_migrations, connect
from btd6.query import UpgradeFilters, build_order_by, build_where, search_upgrades

FIXTURE_PATHS = ["0-0-0", "1-1-0", "2-0-0", "2-1-0"]
STAT_COLUMNS = [
    "range",
    "footprint_radius",
    "attack_rate",
    "projectile_count",
    "projectile_damage",
    "projectile_pierce",
    "projectile_speed",
    "projectile_radius",
    "projectile_lifespan",
    "ability_cooldown",
]


def parse_csv_value(text: str) -> float | None:
    return float(text) if text != "" else None


def load_all_rows(csv_path: Path) -> dict[str, dict]:
    with csv_path.open(newline="") as handle:
        return {row["path"]: row for row in csv.DictReader(handle)}


def load_fixture_rows(csv_path: Path) -> dict[str, dict]:
    rows = load_all_rows(csv_path)
    return {path: rows[path] for path in FIXTURE_PATHS}


def insert_tower(conn: sqlite3.Connection, name: str, category: str) -> int:
    cursor = conn.execute("INSERT INTO towers (name, category) VALUES (?, ?)", (name, category))
    return cursor.lastrowid


def insert_upgrade(
    conn: sqlite3.Connection,
    tower_id: int,
    row: dict,
    path: str | None = None,
    damage_type: str | None = None,
    can_hit_camo: bool | None = None,
    stat_overrides: dict | None = None,
) -> None:
    stats = {column: parse_csv_value(row[column]) for column in STAT_COLUMNS}
    stats.update(stat_overrides or {})
    path = path if path is not None else row["path"]
    damage_type = damage_type if damage_type is not None else row["damage_type"]
    if can_hit_camo is None:
        can_hit_camo = row["can_hit_camo"] == "True"
    type_id = conn.execute("SELECT id FROM damage_types WHERE name = ?", (damage_type,)).fetchone()[
        "id"
    ]
    columns = ["tower_id", "path", "damage_type_id", "can_hit_camo", *stats]
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO upgrades ({', '.join(columns)}) VALUES ({placeholders})",
        [tower_id, path, type_id, int(can_hit_camo), *stats.values()],
    )


def build_database(
    csv_path: Path,
    with_rows: bool = True,
    all_rows: bool = False,
    path: str = ":memory:",
) -> sqlite3.Connection:
    conn = connect(path)
    apply_migrations(conn)
    if with_rows:
        tower_id = insert_tower(conn, "Super Monkey", "Magic")
        loader = load_all_rows if all_rows else load_fixture_rows
        for row in loader(csv_path).values():
            insert_upgrade(conn, tower_id, row)
        conn.commit()
    return conn


def paths_of(result: list[sqlite3.Row]) -> list[str]:
    return [row["path"] for row in result]


def close_after(connection: sqlite3.Connection):
    yield connection
    connection.close()


@pytest.fixture
def conn(golden_csv_path: Path):
    yield from close_after(build_database(golden_csv_path))


@pytest.fixture
def full_conn(golden_csv_path: Path):
    yield from close_after(build_database(golden_csv_path, all_rows=True))


@pytest.fixture
def conn_with_camo_plasma(conn: sqlite3.Connection, golden_csv_path: Path):
    tower_id = conn.execute("SELECT id FROM towers WHERE name = 'Super Monkey'").fetchone()["id"]
    insert_upgrade(conn, tower_id, load_all_rows(golden_csv_path)["2-0-2"])
    conn.commit()
    return conn


@pytest.fixture
def empty_conn(golden_csv_path: Path):
    yield from close_after(build_database(golden_csv_path, with_rows=False))


def add_alchemist_upgrade(
    connection: sqlite3.Connection,
    csv_path: Path,
    path: str,
    damage_type: str,
    can_hit_camo: bool | None = None,
    stat_overrides: dict | None = None,
) -> sqlite3.Connection:
    alchemist_id = insert_tower(connection, "Alchemist", "Magic")
    base_row = load_fixture_rows(csv_path)["0-0-0"]
    insert_upgrade(
        connection,
        alchemist_id,
        base_row,
        path=path,
        damage_type=damage_type,
        can_hit_camo=can_hit_camo,
        stat_overrides=stat_overrides,
    )
    connection.commit()
    return connection


@pytest.fixture
def conn_with_null_pierce(conn: sqlite3.Connection, golden_csv_path: Path):
    return add_alchemist_upgrade(
        conn,
        golden_csv_path,
        "0-0-1",
        "Sharp",
        can_hit_camo=False,
        stat_overrides={"projectile_pierce": None},
    )


FILTER_CASES = [
    pytest.param(0, False, ["0-0-0", "1-1-0"], id="test_search_upgrades_all_base"),
    pytest.param(3, False, ["1-1-0"], id="test_search_upgrades_pierce_inclusive_boundary"),
    pytest.param(4, False, [], id="test_search_upgrades_pierce_above_highest"),
    pytest.param(None, False, ["0-0-0", "1-1-0"], id="test_search_upgrades_pierce_none"),
    pytest.param(0, True, ["2-0-0", "2-1-0"], id="test_search_upgrades_lead_true"),
    pytest.param(0, None, FIXTURE_PATHS, id="test_search_upgrades_lead_none"),
]


@pytest.mark.parametrize(("min_pierce", "can_pop_lead", "expected"), FILTER_CASES)
def test_search_upgrades_filter_cases(conn, min_pierce, can_pop_lead, expected):
    filters = UpgradeFilters(min_pierce=min_pierce, can_pop_lead=can_pop_lead)
    assert paths_of(search_upgrades(conn, filters)) == expected


def test_search_upgrades_pierce_negative(conn):
    filters = UpgradeFilters(min_pierce=-1, can_pop_lead=False)
    with pytest.raises(ValueError, match="min_pierce must be 0 or more, got -1"):
        search_upgrades(conn, filters)


def test_search_upgrades_filters_omitted(conn):
    assert paths_of(search_upgrades(conn)) == FIXTURE_PATHS


def test_search_upgrades_no_filters(conn):
    assert paths_of(search_upgrades(conn, UpgradeFilters())) == FIXTURE_PATHS


def test_search_upgrades_empty_table(empty_conn):
    filters = UpgradeFilters(min_pierce=0, can_pop_lead=False)
    assert paths_of(search_upgrades(empty_conn, filters)) == []


def test_search_upgrades_null_pierce(conn_with_null_pierce):
    filters = UpgradeFilters(min_pierce=0, can_pop_lead=False)
    result = paths_of(search_upgrades(conn_with_null_pierce, filters))
    assert result == ["0-0-0", "1-1-0"]
    assert "0-0-1" not in result


def test_search_upgrades_sort_whitelisted(conn):
    filters = UpgradeFilters(min_pierce=0, can_pop_lead=False)
    result = search_upgrades(conn, filters, sort_by="projectile_pierce")
    assert paths_of(result) == ["1-1-0", "0-0-0"]


def test_search_upgrades_sort_not_whitelisted(conn):
    filters = UpgradeFilters(min_pierce=0, can_pop_lead=False)
    message = re.escape('Cannot sort by "; DROP TABLE upgrades". Allowed: ')
    with pytest.raises(ValueError, match=message):
        search_upgrades(conn, filters, sort_by="; DROP TABLE upgrades")
    assert conn.execute("SELECT COUNT(*) FROM upgrades").fetchone()[0] == 4


def test_search_upgrades_limit_one(conn):
    filters = UpgradeFilters(min_pierce=0, can_pop_lead=False)
    assert paths_of(search_upgrades(conn, filters, limit=1)) == ["0-0-0"]


def test_search_upgrades_limit_zero(conn):
    filters = UpgradeFilters(min_pierce=0, can_pop_lead=False)
    with pytest.raises(ValueError, match="limit must be at least 1, got 0"):
        search_upgrades(conn, filters, limit=0)


def test_search_upgrades_sort_descending_null_last(conn_with_null_pierce):
    result = search_upgrades(conn_with_null_pierce, sort_by="projectile_pierce")
    assert paths_of(result) == ["1-1-0", "2-1-0", "2-0-0", "0-0-0", "0-0-1"]


def test_search_upgrades_sort_ascending_null_last(conn_with_null_pierce):
    result = search_upgrades(conn_with_null_pierce, sort_by="projectile_pierce", descending=False)
    assert paths_of(result) == ["0-0-0", "2-0-0", "1-1-0", "2-1-0", "0-0-1"]


def test_search_upgrades_sort_with_limit(conn):
    result = search_upgrades(conn, sort_by="projectile_pierce", limit=2)
    assert paths_of(result) == ["1-1-0", "2-1-0"]


@pytest.mark.parametrize(
    "column",
    [
        "range",
        "attack_rate",
        "projectile_damage",
        "projectile_pierce",
        "projectile_speed",
        "projectile_count",
        "ability_cooldown",
    ],
)
def test_search_upgrades_sort_every_whitelisted_column(conn, column):
    assert len(search_upgrades(conn, sort_by=column)) == 4


def test_search_upgrades_sort_attack_rate_ascending(conn):
    result = search_upgrades(conn, sort_by="attack_rate", descending=False)
    assert paths_of(result) == ["2-0-0", "2-1-0", "0-0-0", "1-1-0"]


def test_search_upgrades_sort_tie_by_tower_name(conn_with_camo_upgrade):
    result = search_upgrades(conn_with_camo_upgrade, sort_by="range")
    assert paths_of(result) == ["1-1-0", "2-1-0", "0-0-1", "0-0-0", "2-0-0"]


def test_search_upgrades_limit_above_row_count(conn):
    assert paths_of(search_upgrades(conn, limit=10)) == FIXTURE_PATHS


def test_search_upgrades_limit_negative(conn):
    with pytest.raises(ValueError, match="limit must be at least 1, got -1"):
        search_upgrades(conn, limit=-1)


@pytest.fixture
def conn_with_unknown_damage_type(conn: sqlite3.Connection, golden_csv_path: Path):
    return add_alchemist_upgrade(conn, golden_csv_path, "0-0-2", "Unknown")


CAN_POP_CASES = [
    pytest.param(
        {"can_pop_lead": False}, ["0-0-0", "1-1-0"], id="test_search_upgrades_can_pop_lead_false"
    ),
    pytest.param({"can_pop_black": False}, [], id="test_search_upgrades_can_pop_black_false"),
    pytest.param({"can_pop_white": False}, [], id="test_search_upgrades_can_pop_white_false"),
    pytest.param(
        {"can_pop_purple": False},
        ["1-1-0", "2-0-0", "2-1-0"],
        id="test_search_upgrades_can_pop_purple_false",
    ),
    pytest.param(
        {"can_pop_glass": False},
        ["1-1-0", "2-0-0", "2-1-0"],
        id="test_search_upgrades_can_pop_glass_false",
    ),
    pytest.param(
        {"can_pop_frozen": False}, ["0-0-0"], id="test_search_upgrades_can_pop_frozen_false"
    ),
    pytest.param(
        {"can_pop_lead": True}, ["2-0-0", "2-1-0"], id="test_search_upgrades_can_pop_lead_true"
    ),
    pytest.param(
        {"can_pop_lead": False, "can_pop_purple": True},
        ["0-0-0"],
        id="test_search_upgrades_can_pop_two_flags",
    ),
]


@pytest.mark.parametrize(("flags", "expected"), CAN_POP_CASES)
def test_search_upgrades_can_pop_filters(conn, flags, expected):
    assert paths_of(search_upgrades(conn, UpgradeFilters(**flags))) == expected


def test_search_upgrades_can_pop_unknown_false(conn_with_unknown_damage_type):
    result = paths_of(
        search_upgrades(conn_with_unknown_damage_type, UpgradeFilters(can_pop_lead=False))
    )
    assert result == ["0-0-0", "1-1-0"]
    assert "0-0-2" not in result


def test_search_upgrades_can_pop_unknown_true(conn_with_unknown_damage_type):
    result = paths_of(
        search_upgrades(conn_with_unknown_damage_type, UpgradeFilters(can_pop_lead=True))
    )
    assert result == ["2-0-0", "2-1-0"]
    assert "0-0-2" not in result


@pytest.fixture
def conn_with_null_range(conn: sqlite3.Connection, golden_csv_path: Path):
    return add_alchemist_upgrade(
        conn,
        golden_csv_path,
        "0-0-3",
        "Sharp",
        stat_overrides={"range": None},
    )


THRESHOLD_CASES = [
    pytest.param({"min_range": 0}, FIXTURE_PATHS, id="test_search_upgrades_min_range_zero"),
    pytest.param({"min_damage": 0}, FIXTURE_PATHS, id="test_search_upgrades_min_damage_zero"),
    pytest.param(
        {"min_projectile_speed": 0},
        FIXTURE_PATHS,
        id="test_search_upgrades_min_projectile_speed_zero",
    ),
    pytest.param(
        {"min_range": 60},
        ["1-1-0", "2-1-0"],
        id="test_search_upgrades_min_range_inclusive_boundary",
    ),
    pytest.param({"min_range": 61}, [], id="test_search_upgrades_min_range_above_highest"),
    pytest.param(
        {"min_damage": 1},
        FIXTURE_PATHS,
        id="test_search_upgrades_min_damage_inclusive_boundary",
    ),
    pytest.param({"min_damage": 2}, [], id="test_search_upgrades_min_damage_above_highest"),
    pytest.param(
        {"min_projectile_speed": 200},
        FIXTURE_PATHS,
        id="test_search_upgrades_min_projectile_speed_inclusive_boundary",
    ),
]


@pytest.mark.parametrize(("thresholds", "expected"), THRESHOLD_CASES)
def test_search_upgrades_threshold_filters(conn, thresholds, expected):
    assert paths_of(search_upgrades(conn, UpgradeFilters(**thresholds))) == expected


def test_search_upgrades_min_range_negative(conn):
    with pytest.raises(ValueError, match="min_range must be 0 or more, got -1"):
        search_upgrades(conn, UpgradeFilters(min_range=-1))


def test_search_upgrades_min_range_null(conn_with_null_range):
    result = paths_of(search_upgrades(conn_with_null_range, UpgradeFilters(min_range=0)))
    assert result == FIXTURE_PATHS
    assert "0-0-3" not in result


VALID_DAMAGE_TYPES = (
    "Acid, Cold, Energy, Explosion, Fire, Frigid, Glacier, Normal, Plasma, Sharp, Shatter, Unknown"
)
SORT_ALLOWED = (
    "range, attack_rate, projectile_damage, projectile_pierce, projectile_speed, "
    "projectile_count, ability_cooldown"
)


@pytest.fixture
def conn_with_camo_upgrade(conn: sqlite3.Connection, golden_csv_path: Path):
    return add_alchemist_upgrade(conn, golden_csv_path, "0-0-1", "Sharp", can_hit_camo=True)


DAMAGE_TYPE_CASES = [
    pytest.param("Sharp", ["0-0-0"], id="test_search_upgrades_damage_type_sharp"),
    pytest.param("Energy", ["1-1-0"], id="test_search_upgrades_damage_type_energy"),
    pytest.param("Plasma", ["2-0-0", "2-1-0"], id="test_search_upgrades_damage_type_plasma"),
    pytest.param("Normal", [], id="test_search_upgrades_damage_type_valid_no_rows"),
]


@pytest.mark.parametrize(("name", "expected"), DAMAGE_TYPE_CASES)
def test_search_upgrades_damage_type_filter(conn, name, expected):
    assert paths_of(search_upgrades(conn, UpgradeFilters(damage_type=name))) == expected


def test_search_upgrades_damage_type_unknown_name_exact_message(conn):
    expected = f'Unknown damage type "Bogus". Valid types: {VALID_DAMAGE_TYPES}'
    with pytest.raises(ValueError) as excinfo:
        search_upgrades(conn, UpgradeFilters(damage_type="Bogus"))
    assert str(excinfo.value) == expected


@pytest.mark.parametrize("name", ["sharp", "SHARP", "Sharp ", ""])
def test_search_upgrades_damage_type_is_case_and_space_sensitive(conn, name):
    with pytest.raises(ValueError, match="Unknown damage type"):
        search_upgrades(conn, UpgradeFilters(damage_type=name))


def test_search_upgrades_damage_type_combined_with_threshold(conn):
    filters = UpgradeFilters(damage_type="Plasma", min_range=60)
    assert paths_of(search_upgrades(conn, filters)) == ["2-1-0"]


def test_search_upgrades_damage_type_combined_with_can_pop_is_and(conn):
    filters = UpgradeFilters(damage_type="Plasma", can_pop_lead=False)
    assert paths_of(search_upgrades(conn, filters)) == []


def test_search_upgrades_can_hit_camo_true(conn_with_camo_upgrade):
    result = search_upgrades(conn_with_camo_upgrade, UpgradeFilters(can_hit_camo=True))
    assert paths_of(result) == ["0-0-1"]


def test_search_upgrades_can_hit_camo_false(conn_with_camo_upgrade):
    result = search_upgrades(conn_with_camo_upgrade, UpgradeFilters(can_hit_camo=False))
    assert paths_of(result) == FIXTURE_PATHS


def test_search_upgrades_can_hit_camo_combined_with_damage_type(conn_with_camo_upgrade):
    filters = UpgradeFilters(can_hit_camo=True, damage_type="Plasma")
    assert paths_of(search_upgrades(conn_with_camo_upgrade, filters)) == []


def test_search_upgrades_sort_invalid_exact_message(conn):
    with pytest.raises(ValueError) as excinfo:
        search_upgrades(conn, sort_by="bogus")
    assert str(excinfo.value) == f'Cannot sort by "bogus". Allowed: {SORT_ALLOWED}'


def test_build_order_by_descending():
    assert build_order_by("range", True) == (
        " ORDER BY upgrades.range DESC NULLS LAST, towers.name, upgrades.path"
    )


def test_build_order_by_ascending():
    assert build_order_by("range", False) == (
        " ORDER BY upgrades.range ASC NULLS LAST, towers.name, upgrades.path"
    )


def test_build_order_by_no_sort():
    assert build_order_by(None, True) == " ORDER BY towers.name, upgrades.path"


def test_build_where_two_filters_exact_sql(conn):
    filters = UpgradeFilters(tower_name="Super Monkey", min_range=60)
    sql, params = build_where(conn, filters)
    assert sql == " WHERE towers.name = ? AND upgrades.range >= ?"
    assert params == ["Super Monkey", 60]


def test_build_where_no_filters(conn):
    assert build_where(conn, UpgradeFilters()) == ("", [])


def test_search_upgrades_damage_type_plasma_full_data(full_conn):
    result = search_upgrades(full_conn, UpgradeFilters(damage_type="Plasma"))
    assert len(result) == 17
    assert all(row["damage_type"] == "Plasma" for row in result)


def test_search_upgrades_damage_type_and_camo(conn_with_camo_plasma):
    filters = UpgradeFilters(damage_type="Plasma", can_hit_camo=True)
    assert paths_of(search_upgrades(conn_with_camo_plasma, filters)) == ["2-0-2"]


def test_search_upgrades_damage_type_and_no_camo(conn_with_camo_plasma):
    filters = UpgradeFilters(damage_type="Plasma", can_hit_camo=False)
    assert paths_of(search_upgrades(conn_with_camo_plasma, filters)) == ["2-0-0", "2-1-0"]
