from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from btd6.db import MIGRATIONS_DIR, apply_migrations, connect
from btd6.etl.extract import BLOON_FLAG_COLUMNS

FLAG_COLUMNS = list(BLOON_FLAG_COLUMNS)


@pytest.fixture
def migrated() -> Iterator[sqlite3.Connection]:
    connection = connect(":memory:")
    apply_migrations(connection)
    yield connection
    connection.close()


def columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]


def test_migration_005_user_version(migrated) -> None:
    assert migrated.execute("PRAGMA user_version").fetchone()[0] == 5


def test_migration_005_applied_to_version_four_database() -> None:
    connection = connect(":memory:")
    for script in sorted(MIGRATIONS_DIR.glob("00[1234]_*.sql")):
        connection.executescript(script.read_text())
    connection.execute("PRAGMA user_version = 4")
    assert apply_migrations(connection) == ["005_bloon_properties.sql"]
    connection.close()


def test_bloons_gain_property_columns(migrated) -> None:
    assert columns(migrated, "bloons")[-6:] == FLAG_COLUMNS


@pytest.mark.parametrize("column", FLAG_COLUMNS)
def test_bloon_property_defaults_to_zero(migrated: sqlite3.Connection, column: str) -> None:
    migrated.execute("INSERT INTO bloons (name, is_moab) VALUES ('Red', 0)")
    assert migrated.execute(f"SELECT {column} FROM bloons").fetchone()[0] == 0


@pytest.mark.parametrize("column", FLAG_COLUMNS)
@pytest.mark.parametrize(("value", "valid"), [(0, True), (1, True), (2, False), (None, False)])
def test_bloon_property_check(
    migrated: sqlite3.Connection, column: str, value: int | None, valid: bool
) -> None:
    sql = f"INSERT INTO bloons (name, is_moab, {column}) VALUES ('Red', 0, ?)"
    if valid:
        migrated.execute(sql, (value,))
    else:
        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(sql, (value,))
