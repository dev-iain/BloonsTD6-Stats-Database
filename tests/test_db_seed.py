from __future__ import annotations

import pytest

from btd6.db import apply_migrations, connect
from btd6.db.seed import (
    POP_COLUMNS,
    damage_type_rows,
    initialize_database,
    seed_lookup_tables,
)
from btd6.etl.extract import BLOON_PROPERTIES, DAMAGE_TYPES


@pytest.fixture
def migrated_connection():
    connection = connect(":memory:")
    apply_migrations(connection)
    yield connection
    connection.close()


def damage_type_row(connection, name: str):
    return connection.execute("SELECT * FROM damage_types WHERE name = ?", (name,)).fetchone()


def count_types(connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM damage_types").fetchone()[0]


def test_seed_twelve_rows(migrated_connection):
    seed_lookup_tables(migrated_connection)
    assert count_types(migrated_connection) == len(DAMAGE_TYPES) + 1 == 12


def test_seed_sharp_cannot_pop_lead_and_frozen(migrated_connection):
    seed_lookup_tables(migrated_connection)
    row = damage_type_row(migrated_connection, "Sharp")
    assert row["can_pop_lead"] == 0
    assert row["can_pop_frozen"] == 0
    assert row["can_pop_black"] == row["can_pop_white"] == 1


def test_seed_normal_pops_everything(migrated_connection):
    seed_lookup_tables(migrated_connection)
    row = damage_type_row(migrated_connection, "Normal")
    assert [row[column] for column in POP_COLUMNS] == [1] * 6


def test_seed_unknown_flags_are_null(migrated_connection):
    seed_lookup_tables(migrated_connection)
    row = damage_type_row(migrated_connection, "Unknown")
    assert [row[column] for column in POP_COLUMNS] == [None] * 6


def test_seed_twice_same_count(migrated_connection):
    seed_lookup_tables(migrated_connection)
    seed_lookup_tables(migrated_connection)
    assert count_types(migrated_connection) == 12


def test_seed_matches_every_code_entry(migrated_connection):
    seed_lookup_tables(migrated_connection)
    for name, cannot_pop in DAMAGE_TYPES.values():
        row = damage_type_row(migrated_connection, name)
        for bloon_property in BLOON_PROPERTIES:
            expected = int(bloon_property not in cannot_pop)
            assert row[f"can_pop_{bloon_property.lower()}"] == expected, name


def test_seed_new_code_entry_appears_without_sql(migrated_connection, monkeypatch):
    extended = {**DAMAGE_TYPES, 200: ("Testium", {"Lead"})}
    monkeypatch.setattr("btd6.db.seed.DAMAGE_TYPES", extended)
    seed_lookup_tables(migrated_connection)
    row = damage_type_row(migrated_connection, "Testium")
    assert row["can_pop_lead"] == 0
    assert row["can_pop_black"] == 1
    assert count_types(migrated_connection) == 13
    assert damage_type_row(migrated_connection, "Normal")["id"] == 1


def test_seed_without_migration_fails():
    connection = connect(":memory:")
    with pytest.raises(Exception, match="no such table"):
        seed_lookup_tables(connection)
    connection.close()


def test_initialize_database_migrates_and_seeds():
    connection = connect(":memory:")
    initialize_database(connection)
    initialize_database(connection)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
    assert count_types(connection) == 12
    connection.close()


def test_migration_damage_types_match_seed_rows(migrated_connection):
    columns = ", ".join(["name", *POP_COLUMNS])
    rows = migrated_connection.execute(f"SELECT id, {columns} FROM damage_types").fetchall()
    assert all(row["id"] is not None for row in rows)
    actual = {row["name"]: tuple(row)[2:] for row in rows}
    expected = {name: tuple(flags) for name, *flags in damage_type_rows()}
    assert actual == expected
