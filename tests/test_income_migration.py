from __future__ import annotations

import sqlite3

import pytest

from btd6.db import MIGRATIONS_DIR, apply_migrations, connect


@pytest.fixture
def migrated() -> sqlite3.Connection:
    connection = connect(":memory:")
    apply_migrations(connection)
    yield connection
    connection.close()


def columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]


def attempt(connection: sqlite3.Connection, sql: str, params: tuple, valid: bool) -> None:
    if valid:
        connection.execute(sql, params)
    else:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(sql, params)


def test_migration_004_user_version(migrated) -> None:
    assert migrated.execute("PRAGMA user_version").fetchone()[0] == 4


def test_migration_004_applied_to_version_three_database() -> None:
    connection = connect(":memory:")
    for script in sorted(MIGRATIONS_DIR.glob("00[123]_*.sql")):
        connection.executescript(script.read_text())
    connection.execute("PRAGMA user_version = 3")
    assert apply_migrations(connection) == ["004_income.sql"]
    connection.close()


def test_income_tables_exist(migrated) -> None:
    assert columns(migrated, "income_thresholds") == ["max_round", "multiplier"]
    assert columns(migrated, "income_settings") == ["id", "final_multiplier"]


def test_bloons_gain_pop_cash_columns(migrated) -> None:
    assert columns(migrated, "bloons")[-2:] == ["pop_cash", "pop_cash_super"]


def test_bloons_pop_cash_defaults_to_null(migrated) -> None:
    migrated.execute("INSERT INTO bloons (name, is_moab) VALUES ('Red', 0)")
    row = migrated.execute("SELECT pop_cash, pop_cash_super FROM bloons").fetchone()
    assert (row["pop_cash"], row["pop_cash_super"]) == (None, None)


@pytest.mark.parametrize("column", ["pop_cash", "pop_cash_super"])
@pytest.mark.parametrize(("value", "valid"), [(0, True), (1, True), (-1, False)])
def test_bloons_pop_cash_check(migrated, column, value, valid) -> None:
    sql = f"INSERT INTO bloons (name, is_moab, {column}) VALUES ('Red', 0, ?)"
    attempt(migrated, sql, (value,), valid)


@pytest.mark.parametrize(("max_round", "valid"), [(1, True), (50, True), (0, False), (-1, False)])
def test_income_thresholds_max_round_check(migrated, max_round, valid) -> None:
    sql = "INSERT INTO income_thresholds (max_round, multiplier) VALUES (?, 1)"
    attempt(migrated, sql, (max_round,), valid)


@pytest.mark.parametrize(("multiplier", "valid"), [(0, True), (0.5, True), (-0.1, False)])
def test_income_thresholds_multiplier_check(migrated, multiplier, valid) -> None:
    sql = "INSERT INTO income_thresholds (max_round, multiplier) VALUES (50, ?)"
    attempt(migrated, sql, (multiplier,), valid)


def test_income_thresholds_max_round_unique(migrated) -> None:
    migrated.execute("INSERT INTO income_thresholds VALUES (50, 1)")
    with pytest.raises(sqlite3.IntegrityError):
        migrated.execute("INSERT INTO income_thresholds VALUES (50, 0.5)")


@pytest.mark.parametrize(
    ("row_id", "final", "valid"), [(1, 0.02, True), (2, 0.02, False), (1, -1, False)]
)
def test_income_settings_checks(migrated, row_id, final, valid) -> None:
    sql = "INSERT INTO income_settings (id, final_multiplier) VALUES (?, ?)"
    attempt(migrated, sql, (row_id, final), valid)
