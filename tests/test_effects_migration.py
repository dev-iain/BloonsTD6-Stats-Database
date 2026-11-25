from __future__ import annotations

import sqlite3

import pytest

from btd6.db import MIGRATIONS_DIR, apply_migrations, connect

EFFECT_COLUMNS = [
    "id",
    "projectile_id",
    "effect_index",
    "name",
    "damage",
    "tick_interval",
    "lifespan",
    "trigger_immediate",
    "moab_bonus_damage",
    "moab_only",
    "damage_type_id",
]


@pytest.fixture
def migrated() -> sqlite3.Connection:
    connection = connect(":memory:")
    apply_migrations(connection)
    connection.execute(
        "INSERT INTO towers (id, name, category) VALUES (1, 'Glue Gunner', 'Support')"
    )
    connection.execute(
        "INSERT INTO upgrades (id, tower_id, path, damage_type_id, can_hit_camo)"
        " VALUES (1, 1, '2-0-0', 1, 1)"
    )
    connection.execute(
        "INSERT INTO attacks (id, upgrade_id, attack_index, name) VALUES (1, 1, 0, 'Attack')"
    )
    connection.execute(
        "INSERT INTO projectiles (id, attack_id, projectile_index, name, damage_type_id,"
        " can_hit_camo) VALUES (1, 1, 0, 'Projectile', 1, 1)"
    )
    yield connection
    connection.close()


def insert_effect(connection: sqlite3.Connection, **fields) -> None:
    values = {
        "projectile_id": 1,
        "effect_index": 0,
        "name": "Damage over time",
        "damage": 1,
        "tick_interval": 2,
        "lifespan": 11,
        "trigger_immediate": 0,
        "damage_type_id": 1,
    }
    values.update(fields)
    marks = ", ".join("?" * len(values))
    connection.execute(
        f"INSERT INTO projectile_effects ({', '.join(values)}) VALUES ({marks})",
        tuple(values.values()),
    )


def attempt(action, valid: bool) -> None:
    if valid:
        action()
    else:
        with pytest.raises(sqlite3.IntegrityError):
            action()


def effect_count(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM projectile_effects").fetchone()[0]


def test_migration_007_script_exists() -> None:
    assert (MIGRATIONS_DIR / "007_projectile_effects.sql").exists()


def test_migration_007_user_version() -> None:
    connection = connect(":memory:")
    assert apply_migrations(connection)[-1] == "007_projectile_effects.sql"
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
    connection.close()


def test_migration_007_applied_to_version_six_database() -> None:
    connection = connect(":memory:")
    for script in sorted(MIGRATIONS_DIR.glob("00[1-6]_*.sql")):
        connection.executescript(script.read_text())
    connection.execute("PRAGMA user_version = 6")
    assert apply_migrations(connection) == ["007_projectile_effects.sql"]
    connection.close()


def test_projectile_effects_columns(migrated) -> None:
    names = [row["name"] for row in migrated.execute("PRAGMA table_info(projectile_effects)")]
    assert names == EFFECT_COLUMNS


def test_projectile_effects_defaults(migrated) -> None:
    insert_effect(migrated)
    row = migrated.execute("SELECT * FROM projectile_effects").fetchone()
    assert (row["moab_bonus_damage"], row["moab_only"]) == (None, 0)


@pytest.mark.parametrize(
    ("column", "value", "valid"),
    [
        ("effect_index", 0, True),
        ("effect_index", -1, False),
        ("damage", 0.5, True),
        ("damage", 0, False),
        ("damage", -1, False),
        ("tick_interval", 0.01, True),
        ("tick_interval", 0, False),
        ("tick_interval", -1, False),
        ("lifespan", 0, True),
        ("lifespan", 0.95, True),
        ("lifespan", -0.1, False),
        ("trigger_immediate", 1, True),
        ("trigger_immediate", 2, False),
        ("trigger_immediate", -1, False),
        ("moab_bonus_damage", None, True),
        ("moab_bonus_damage", 0, True),
        ("moab_bonus_damage", 3, True),
        ("moab_bonus_damage", -1, False),
        ("moab_only", 1, True),
        ("moab_only", 2, False),
    ],
)
def test_projectile_effect_checks(migrated, column, value, valid) -> None:
    attempt(lambda: insert_effect(migrated, **{column: value}), valid)


@pytest.mark.parametrize(
    "column", ["projectile_id", "effect_index", "name", "damage", "tick_interval", "lifespan"]
)
def test_projectile_effect_required_columns(migrated, column) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_effect(migrated, **{column: None})


@pytest.mark.parametrize("column", ["trigger_immediate", "damage_type_id"])
def test_projectile_effect_required_flags(migrated, column) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_effect(migrated, **{column: None})


def test_projectile_effect_projectile_must_exist(migrated) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_effect(migrated, projectile_id=99)


def test_projectile_effect_damage_type_must_exist(migrated) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_effect(migrated, damage_type_id=999)


def test_projectile_effect_unique_per_projectile_index(migrated) -> None:
    insert_effect(migrated)
    with pytest.raises(sqlite3.IntegrityError):
        insert_effect(migrated, name="Other")
    insert_effect(migrated, effect_index=1)


@pytest.mark.parametrize(
    "delete",
    [
        "DELETE FROM projectiles WHERE id = 1",
        "DELETE FROM attacks WHERE id = 1",
        "DELETE FROM upgrades WHERE id = 1",
        "DELETE FROM towers WHERE id = 1",
    ],
)
def test_deleting_parent_deletes_effects(migrated, delete) -> None:
    insert_effect(migrated)
    migrated.execute(delete)
    assert effect_count(migrated) == 0
