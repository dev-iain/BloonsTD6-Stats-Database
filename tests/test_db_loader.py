from __future__ import annotations

import sqlite3
from typing import Any

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.db import connect
from btd6.db.loader import UPGRADE_COLUMNS, ensure_tower, load_tower, upgrade_params
from btd6.db.seed import initialize_database
from tests.factories import StatsFactory

UPGRADE_QUERY = """
    SELECT t.name AS tower, t.category, u.path, u.range, u.projectile_pierce,
           u.attack_rate, u.projectile_damage, u.ability_cooldown, u.can_hit_camo,
           d.name AS damage_type
    FROM upgrades u
    JOIN towers t ON t.id = u.tower_id
    JOIN damage_types d ON d.id = u.damage_type_id
    ORDER BY t.name, u.path
"""


def base_stats(**overrides: Any) -> dict[str, Any]:
    params = {"mask": 73, "invisible": True, "pierce": 2, "damage": 1, "rate": 0.045}
    params.update(overrides)
    return StatsFactory(**params)


def count_rows(connection: sqlite3.Connection, table: str) -> int:
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def fetch_upgrade(connection: sqlite3.Connection, tower: str, path: str) -> sqlite3.Row:
    rows = [row for row in connection.execute(UPGRADE_QUERY) if (row[0], row[2]) == (tower, path)]
    assert len(rows) == 1
    return rows[0]


def snapshot(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in connection.execute(UPGRADE_QUERY)]


def test_load_tower_all_base(database: sqlite3.Connection) -> None:
    written = load_tower(database, "Super Monkey", {"_100": base_stats()}, category="Magic")
    row = fetch_upgrade(database, "Super Monkey", "1-0-0")
    assert written == 1
    assert count_rows(database, "towers") == 1
    assert count_rows(database, "upgrades") == 1
    assert (row["range"], row["projectile_pierce"], row["can_hit_camo"]) == (50.0, 2.0, 0)
    assert (row["damage_type"], row["category"]) == ("Energy", "Magic")


def test_load_tower_default_category_is_primary(database: sqlite3.Connection) -> None:
    load_tower(database, "Dart Monkey", {"_100": base_stats()})
    assert fetch_upgrade(database, "Dart Monkey", "1-0-0")["category"] == "Primary"


def test_load_tower_empty_resolved(database: sqlite3.Connection) -> None:
    assert load_tower(database, "Super Monkey", {}) == 0
    assert count_rows(database, "upgrades") == 0


def test_load_tower_full_tower(
    database: sqlite3.Connection, super_monkey_resolved: dict[str, Any]
) -> None:
    assert load_tower(database, "Super Monkey", super_monkey_resolved) == 64
    assert count_rows(database, "upgrades") == 64
    assert count_rows(database, "towers") == 1
    row = fetch_upgrade(database, "Super Monkey", "5-0-0")
    assert (row["range"], row["projectile_pierce"], row["damage_type"]) == (65.0, 20.0, "Normal")


def test_load_tower_twice_is_idempotent(database: sqlite3.Connection) -> None:
    load_tower(database, "Super Monkey", {"_100": base_stats()})
    assert load_tower(database, "Super Monkey", {"_100": base_stats()}) == 1
    assert count_rows(database, "upgrades") == 1
    assert count_rows(database, "towers") == 1


def test_load_tower_updates_changed_values(database: sqlite3.Connection) -> None:
    load_tower(database, "Super Monkey", {"_100": base_stats()})
    assert load_tower(database, "Super Monkey", {"_100": base_stats(pierce=7, range=99)}) == 1
    row = fetch_upgrade(database, "Super Monkey", "1-0-0")
    assert count_rows(database, "upgrades") == 1
    assert (row["range"], row["projectile_pierce"]) == (99.0, 7.0)


def test_load_tower_removes_upgrades_absent_from_new_data(database: sqlite3.Connection) -> None:
    load_tower(database, "Super Monkey", {"_100": base_stats(), "_200": base_stats()})
    assert load_tower(database, "Super Monkey", {"_200": base_stats()}) == 1
    assert [row["path"] for row in database.execute(UPGRADE_QUERY)] == ["2-0-0"]


def test_load_tower_existing_tower_row(database: sqlite3.Connection) -> None:
    database.execute("INSERT INTO towers (name, category) VALUES ('Super Monkey', 'Magic')")
    assert load_tower(database, "Super Monkey", {"_100": base_stats()}) == 1
    assert count_rows(database, "towers") == 1
    assert count_rows(database, "upgrades") == 1


def test_load_tower_same_path_other_tower(database: sqlite3.Connection) -> None:
    load_tower(database, "Wizard Monkey", {"_100": base_stats(range=11)})
    assert load_tower(database, "Super Monkey", {"_100": base_stats()}) == 1
    pairs = [(row["tower"], row["range"]) for row in database.execute(UPGRADE_QUERY)]
    assert pairs == [("Super Monkey", 50.0), ("Wizard Monkey", 11.0)]


def test_two_towers_coexist(
    database: sqlite3.Connection, super_monkey_resolved: dict[str, Any]
) -> None:
    load_tower(database, "Super Monkey", super_monkey_resolved)
    load_tower(database, "Wizard Monkey", super_monkey_resolved)
    for tower in ("Super Monkey", "Wizard Monkey"):
        query = (
            "SELECT COUNT(*) FROM upgrades u JOIN towers t ON t.id = u.tower_id WHERE t.name = ?"
        )
        assert database.execute(query, (tower,)).fetchone()[0] == 64
        assert fetch_upgrade(database, tower, "0-0-0")["path"] == "0-0-0"
    assert count_rows(database, "upgrades") == 128


def test_reloading_one_tower_leaves_other_untouched(database: sqlite3.Connection) -> None:
    load_tower(database, "Wizard Monkey", {"_100": base_stats(range=11)})
    load_tower(database, "Super Monkey", {"_100": base_stats()})
    load_tower(database, "Super Monkey", {})
    assert [row["tower"] for row in database.execute(UPGRADE_QUERY)] == ["Wizard Monkey"]


def test_load_tower_null_values(database: sqlite3.Connection) -> None:
    stats = {"range": 50, "attacks": {"_order": []}}
    assert load_tower(database, "Super Monkey", {"_100": stats}) == 1
    row = fetch_upgrade(database, "Super Monkey", "1-0-0")
    assert (row["range"], row["can_hit_camo"], row["damage_type"]) == (50.0, 1, "Normal")
    for column in ("attack_rate", "projectile_damage", "projectile_pierce", "ability_cooldown"):
        assert row[column] is None
        query = f"SELECT COUNT(*) FROM upgrades WHERE {column} IS NULL"
        assert database.execute(query).fetchone()[0] == 1


def test_load_tower_unknown_damage_type(database: sqlite3.Connection) -> None:
    assert load_tower(database, "Super Monkey", {"_100": base_stats(mask=3)}) == 1
    assert fetch_upgrade(database, "Super Monkey", "1-0-0")["damage_type"] == "Unknown"
    query = "SELECT can_pop_lead FROM damage_types WHERE name = 'Unknown'"
    assert database.execute(query).fetchone()[0] is None


def test_load_tower_failure_rolls_back(database: sqlite3.Connection) -> None:
    resolved = {"_100": base_stats(), "_200": base_stats(range=-1)}
    with pytest.raises(sqlite3.IntegrityError):
        load_tower(database, "Super Monkey", resolved)
    assert count_rows(database, "upgrades") == 0
    assert count_rows(database, "towers") == 0


def test_load_tower_failure_keeps_previous_contents(database: sqlite3.Connection) -> None:
    load_tower(database, "Super Monkey", {"_100": base_stats()})
    resolved = {"_100": base_stats(range=60), "_200": base_stats(range=-1)}
    with pytest.raises(sqlite3.IntegrityError):
        load_tower(database, "Super Monkey", resolved)
    assert count_rows(database, "upgrades") == 1
    assert fetch_upgrade(database, "Super Monkey", "1-0-0")["range"] == 50.0


def test_ensure_tower_is_idempotent(database: sqlite3.Connection) -> None:
    first_id = ensure_tower(database, "Wizard Monkey", "Magic")
    assert ensure_tower(database, "Wizard Monkey", "Magic") == first_id
    assert count_rows(database, "towers") == 1
    row = database.execute("SELECT id FROM towers WHERE name = 'Wizard Monkey'").fetchone()
    assert row["id"] == first_id


def test_ensure_tower_distinct_ids(database: sqlite3.Connection) -> None:
    assert ensure_tower(database, "Wizard Monkey", "Magic") != ensure_tower(
        database, "Super Monkey", "Magic"
    )


def test_deleting_tower_cascades_upgrades(database: sqlite3.Connection) -> None:
    load_tower(database, "Super Monkey", {"_100": base_stats()})
    load_tower(database, "Wizard Monkey", {"_100": base_stats()})
    database.execute("DELETE FROM towers WHERE name = 'Super Monkey'")
    assert [row["tower"] for row in database.execute(UPGRADE_QUERY)] == ["Wizard Monkey"]


@pytest.mark.parametrize(
    ("code", "path"), [("_000", "0-0-0"), ("_100", "1-0-0"), ("_210", "2-1-0")]
)
def test_loaded_rows_match_golden_csv(
    database: sqlite3.Connection,
    super_monkey_resolved: dict[str, Any],
    golden_csv_path: Any,
    code: str,
    path: str,
) -> None:
    load_tower(database, "Super Monkey", super_monkey_resolved)
    golden = pd.read_csv(golden_csv_path).set_index("path").loc[path]
    row = fetch_upgrade(database, "Super Monkey", path)
    assert code in super_monkey_resolved
    assert row["range"] == golden["range"]
    assert row["projectile_pierce"] == golden["projectile_pierce"]
    assert row["attack_rate"] == golden["attack_rate"]
    assert row["damage_type"] == golden["damage_type"]
    assert row["can_hit_camo"] == int(golden["can_hit_camo"])


def test_null_ability_cooldown_is_sql_null(
    database: sqlite3.Connection, super_monkey_resolved: dict[str, Any]
) -> None:
    load_tower(database, "Super Monkey", super_monkey_resolved)
    row = fetch_upgrade(database, "Super Monkey", "0-0-0")
    assert row["ability_cooldown"] is None
    query = "SELECT COUNT(*) FROM upgrades WHERE ability_cooldown = 'nan' OR ability_cooldown = ''"
    assert database.execute(query).fetchone()[0] == 0


resolved_strategy = st.dictionaries(
    keys=st.from_regex(r"_[0-5]{3}", fullmatch=True),
    values=st.builds(
        base_stats,
        mask=st.sampled_from([0, 1, 2, 17, 73, 3]),
        invisible=st.booleans(),
        pierce=st.integers(0, 500),
        range=st.integers(0, 200),
    ),
    max_size=8,
)


@settings(max_examples=40, deadline=None)
@given(resolved=resolved_strategy)
def test_reload_is_idempotent_property(resolved: dict[str, Any]) -> None:
    connection = connect(":memory:")
    initialize_database(connection)
    first_count = load_tower(connection, "Super Monkey", resolved)
    after_once = snapshot(connection)
    second_count = load_tower(connection, "Super Monkey", resolved)
    assert first_count == second_count == len(resolved)
    assert snapshot(connection) == after_once
    connection.close()


def test_upgrade_params_unmapped_damage_type_falls_back_to_unknown() -> None:
    type_ids = {"Unknown": 901}
    params = upgrade_params(7, type_ids, "_000", base_stats(mask=0))
    assert params[:2] == (7, 901)


def test_upgrade_params_uses_mapped_damage_type_id() -> None:
    params = upgrade_params(7, {"Normal": 5, "Unknown": 901}, "_000", base_stats(mask=0))
    assert params[1] == 5


@pytest.mark.parametrize(("invisible", "expected"), [(True, 0), (False, 1)])
def test_upgrade_params_passes_booleans_as_plain_ints(invisible: bool, expected: int) -> None:
    params = upgrade_params(
        1, {"Normal": 2, "Unknown": 3}, "_000", base_stats(mask=0, invisible=invisible)
    )
    camo_value = params[2 + UPGRADE_COLUMNS.index("can_hit_camo")]
    assert type(camo_value) is int
    assert camo_value == expected
