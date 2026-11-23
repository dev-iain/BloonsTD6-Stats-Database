from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

import btd6.db
from btd6.db import apply_migrations, connect

EXPECTED_TABLES = ["damage_types", "towers", "upgrade_costs", "upgrades"]


def scalar(connection: sqlite3.Connection, sql: str):
    return connection.execute(sql).fetchone()[0]


def table_names(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def insert_tower_and_upgrade(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO towers (id, name, category) VALUES (1, 'Super Monkey', 'Magic')"
    )
    connection.execute(
        "INSERT INTO upgrades (tower_id, path, damage_type_id, can_hit_camo) "
        "VALUES (1, '1-0-0', 1, 1)"
    )


def write_migrations(directory: Path, scripts: dict[str, str]) -> None:
    for name, body in scripts.items():
        (directory / name).write_text(body)


@pytest.fixture
def memory_connection():
    connection = connect(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def fake_migrations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "migrations"
    directory.mkdir()
    monkeypatch.setattr(btd6.db, "MIGRATIONS_DIR", directory)
    return directory


def test_connect_all_base(memory_connection):
    assert scalar(memory_connection, "PRAGMA foreign_keys") == 1
    assert memory_connection.row_factory is sqlite3.Row
    apply_migrations(memory_connection)
    insert_tower_and_upgrade(memory_connection)
    assert scalar(memory_connection, "SELECT COUNT(*) FROM upgrades") == 1
    row = memory_connection.execute("SELECT name FROM damage_types WHERE id = 1").fetchone()
    assert row["name"] == "Normal"


def test_connect_new_file(tmp_path):
    path = tmp_path / "new.db"
    connection = connect(path)
    try:
        assert path.exists()
        assert scalar(connection, "PRAGMA user_version") == 0
        assert table_names(connection) == []
        assert scalar(connection, "PRAGMA foreign_keys") == 1
    finally:
        connection.close()


def test_connect_existing_migrated_file(tmp_path):
    path = str(tmp_path / "done.db")
    first = connect(path)
    apply_migrations(first)
    first.commit()
    first.close()
    second = connect(path)
    try:
        assert scalar(second, "PRAGMA user_version") == 2
        assert scalar(second, "SELECT COUNT(*) FROM damage_types") == 12
        assert scalar(second, "PRAGMA foreign_keys") == 1
    finally:
        second.close()


def test_connect_missing_parent_directory(tmp_path):
    with pytest.raises(sqlite3.OperationalError, match="^unable to open database file$"):
        connect(tmp_path / "nope" / "x.db")
    assert not (tmp_path / "nope").exists()


def test_connect_row_access_by_index(memory_connection):
    apply_migrations(memory_connection)
    row = memory_connection.execute("SELECT id, name FROM damage_types WHERE id = 1").fetchone()
    assert row[0] == 1
    assert row[1] == "Normal"
    assert tuple(row) == (1, "Normal")
    assert row.keys() == ["id", "name"]


def test_connect_foreign_key_missing_tower(memory_connection):
    apply_migrations(memory_connection)
    with pytest.raises(sqlite3.IntegrityError, match="^FOREIGN KEY constraint failed$"):
        memory_connection.execute(
            "INSERT INTO upgrades (tower_id, path, damage_type_id, can_hit_camo) "
            "VALUES (999, '1-0-0', 1, 1)"
        )
    assert scalar(memory_connection, "SELECT COUNT(*) FROM upgrades") == 0


def test_connect_foreign_key_cascade_delete(memory_connection):
    apply_migrations(memory_connection)
    insert_tower_and_upgrade(memory_connection)
    memory_connection.execute("DELETE FROM towers WHERE id = 1")
    assert scalar(memory_connection, "SELECT COUNT(*) FROM upgrades") == 0


def test_apply_migrations_fresh_database(memory_connection):
    assert apply_migrations(memory_connection) == ["001_initial.sql", "002_costs.sql"]
    assert scalar(memory_connection, "PRAGMA user_version") == 2
    assert table_names(memory_connection) == EXPECTED_TABLES
    assert scalar(memory_connection, "SELECT COUNT(*) FROM damage_types") == 12
    assert scalar(memory_connection, "SELECT COUNT(*) FROM towers") == 0


def test_apply_migrations_already_latest(tmp_path):
    path = tmp_path / "latest.db"
    first = connect(path)
    apply_migrations(first)
    first.commit()
    first.close()
    second = connect(path)
    try:
        assert apply_migrations(second) == []
        assert scalar(second, "PRAGMA user_version") == 2
        assert scalar(second, "SELECT COUNT(*) FROM damage_types") == 12
    finally:
        second.close()


def test_apply_migrations_older_version(memory_connection, fake_migrations):
    write_migrations(
        fake_migrations, {"001_a.sql": "create table a(x);", "002_b.sql": "create table b(y);"}
    )
    memory_connection.execute("create table a(x)")
    memory_connection.execute("PRAGMA user_version = 1")
    assert apply_migrations(memory_connection) == ["002_b.sql"]
    assert scalar(memory_connection, "PRAGMA user_version") == 2
    assert table_names(memory_connection) == ["a", "b"]


def test_apply_migrations_two_underscore_name_after_applied_first(
    memory_connection, fake_migrations
):
    write_migrations(
        fake_migrations,
        {"001_a.sql": "create table a(x);", "002_add_col_x.sql": "alter table a add column z;"},
    )
    memory_connection.execute("create table a(x)")
    memory_connection.execute("PRAGMA user_version = 1")
    assert apply_migrations(memory_connection) == ["002_add_col_x.sql"]
    assert scalar(memory_connection, "PRAGMA user_version") == 2
    columns = [row["name"] for row in memory_connection.execute("PRAGMA table_info(a)")]
    assert columns == ["x", "z"]


def test_apply_migrations_newer_version(memory_connection):
    memory_connection.execute("PRAGMA user_version = 9")
    assert apply_migrations(memory_connection) == []
    assert scalar(memory_connection, "PRAGMA user_version") == 9
    assert table_names(memory_connection) == []


def test_apply_migrations_twice(memory_connection):
    assert apply_migrations(memory_connection) == ["001_initial.sql", "002_costs.sql"]
    assert apply_migrations(memory_connection) == []
    assert scalar(memory_connection, "PRAGMA user_version") == 2
    assert scalar(memory_connection, "SELECT COUNT(*) FROM damage_types") == 12


def test_apply_migrations_failing_script(memory_connection, fake_migrations):
    write_migrations(
        fake_migrations,
        {
            "001_a.sql": "create table a(x);",
            "002_bad.sql": "create table c(z); insert into missing values (1);",
        },
    )
    with pytest.raises(sqlite3.OperationalError, match="^no such table: missing$"):
        apply_migrations(memory_connection)
    assert scalar(memory_connection, "PRAGMA user_version") == 1
    assert "a" in table_names(memory_connection)
    with pytest.raises(sqlite3.OperationalError):
        apply_migrations(memory_connection)
    assert scalar(memory_connection, "PRAGMA user_version") == 1


BAD_SCRIPT = "create table c(z); insert into missing values (1);"


def test_apply_migrations_failure_leaves_no_partial_ddl(memory_connection, fake_migrations):
    write_migrations(fake_migrations, {"001_bad.sql": BAD_SCRIPT})
    with pytest.raises(sqlite3.OperationalError):
        apply_migrations(memory_connection)
    assert "c" not in table_names(memory_connection)
    assert scalar(memory_connection, "PRAGMA user_version") == 0


def test_apply_migrations_rerun_after_fixing_script(memory_connection, fake_migrations):
    write_migrations(fake_migrations, {"001_bad.sql": BAD_SCRIPT})
    with pytest.raises(sqlite3.OperationalError):
        apply_migrations(memory_connection)
    write_migrations(fake_migrations, {"001_bad.sql": "create table c(z);"})
    assert apply_migrations(memory_connection) == ["001_bad.sql"]
    assert "c" in table_names(memory_connection)
    assert scalar(memory_connection, "PRAGMA user_version") == 1


def test_apply_migrations_second_script_fails_keeps_first(memory_connection, fake_migrations):
    write_migrations(
        fake_migrations, {"001_a.sql": "create table a(x);", "002_bad.sql": BAD_SCRIPT}
    )
    with pytest.raises(sqlite3.OperationalError):
        apply_migrations(memory_connection)
    assert table_names(memory_connection) == ["a"]
    assert scalar(memory_connection, "PRAGMA user_version") == 1


@given(calls=st.integers(min_value=1, max_value=5))
def test_apply_migrations_idempotent_property(calls):
    connection = connect(":memory:")
    try:
        results = [apply_migrations(connection) for _ in range(calls)]
        assert results[0] == ["001_initial.sql", "002_costs.sql"]
        assert all(result == [] for result in results[1:])
        assert scalar(connection, "PRAGMA user_version") == 2
    finally:
        connection.close()
