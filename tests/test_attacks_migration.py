from __future__ import annotations

import sqlite3

import pytest

from btd6.db import MIGRATIONS_DIR, apply_migrations, connect

ATTACK_COLUMNS = ["id", "upgrade_id", "attack_index", "name", "rate"]
PROJECTILE_COLUMNS = [
    "id",
    "attack_id",
    "projectile_index",
    "name",
    "damage",
    "pierce",
    "unlimited_damage",
    "unlimited_pierce",
    "moab_bonus_damage",
    "moab_only",
    "count",
    "speed",
    "radius",
    "lifespan",
    "damage_type_id",
    "can_hit_camo",
]
NULLABLE_NUMBERS = ["damage", "pierce", "moab_bonus_damage", "count", "speed", "radius", "lifespan"]


@pytest.fixture
def migrated() -> sqlite3.Connection:
    connection = connect(":memory:")
    apply_migrations(connection)
    connection.execute("INSERT INTO towers (id, name, category) VALUES (1, 'Ninja', 'Primary')")
    connection.execute(
        "INSERT INTO upgrades (id, tower_id, path, damage_type_id, can_hit_camo)"
        " VALUES (1, 1, '0-0-3', 1, 1)"
    )
    connection.execute(
        "INSERT INTO attacks (id, upgrade_id, attack_index, name) VALUES (1, 1, 0, 'A')"
    )
    yield connection
    connection.close()


def columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]


def insert_projectile(connection: sqlite3.Connection, **fields) -> None:
    values = {"attack_id": 1, "projectile_index": 0, "name": "P", "damage_type_id": 1}
    values.update({"can_hit_camo": 1, **fields})
    names = ", ".join(values)
    marks = ", ".join("?" * len(values))
    connection.execute(
        f"INSERT INTO projectiles ({names}) VALUES ({marks})", tuple(values.values())
    )


def attempt(action, valid: bool) -> None:
    if valid:
        action()
    else:
        with pytest.raises(sqlite3.IntegrityError):
            action()


def test_migration_006_is_latest_script() -> None:
    assert (MIGRATIONS_DIR / "006_attacks.sql").exists()


def test_migration_006_user_version() -> None:
    connection = connect(":memory:")
    assert apply_migrations(connection)[-1] == "006_attacks.sql"
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
    connection.close()


def test_migration_006_applied_to_version_five_database() -> None:
    connection = connect(":memory:")
    for script in sorted(MIGRATIONS_DIR.glob("00[1-5]_*.sql")):
        connection.executescript(script.read_text())
    connection.execute("PRAGMA user_version = 5")
    assert apply_migrations(connection) == ["006_attacks.sql"]
    connection.close()


def test_attack_tables_exist(migrated) -> None:
    assert columns(migrated, "attacks") == ATTACK_COLUMNS
    assert columns(migrated, "projectiles") == PROJECTILE_COLUMNS


def test_projectile_defaults(migrated) -> None:
    migrated.execute(
        "INSERT INTO projectiles (attack_id, projectile_index, name, damage_type_id,"
        " can_hit_camo) VALUES (1, 0, 'P', 1, 1)"
    )
    row = migrated.execute("SELECT * FROM projectiles").fetchone()
    assert (row["unlimited_damage"], row["unlimited_pierce"], row["moab_only"]) == (0, 0, 0)
    for column in NULLABLE_NUMBERS:
        assert row[column] is None


@pytest.mark.parametrize(("index", "valid"), [(0, True), (1, True), (-1, False)])
def test_attack_index_check(migrated, index, valid) -> None:
    migrated.execute(
        "INSERT INTO upgrades (id, tower_id, path, damage_type_id, can_hit_camo)"
        " VALUES (2, 1, '0-0-4', 1, 1)"
    )
    statement = "INSERT INTO attacks (upgrade_id, attack_index, name) VALUES (2, ?, 'B')"
    attempt(lambda: migrated.execute(statement, (index,)), valid)


@pytest.mark.parametrize(("rate", "valid"), [(None, True), (0, True), (0.62, True), (-0.1, False)])
def test_attack_rate_check(migrated, rate, valid) -> None:
    statement = "INSERT INTO attacks (upgrade_id, attack_index, name, rate) VALUES (1, 5, 'B', ?)"
    attempt(lambda: migrated.execute(statement, (rate,)), valid)


def test_attack_name_not_null(migrated) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        migrated.execute("INSERT INTO attacks (upgrade_id, attack_index) VALUES (1, 3)")


def test_attack_upgrade_id_must_exist(migrated) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        migrated.execute("INSERT INTO attacks (upgrade_id, attack_index, name) VALUES (99, 0, 'B')")


def test_attack_unique_per_upgrade_index(migrated) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        migrated.execute("INSERT INTO attacks (upgrade_id, attack_index, name) VALUES (1, 0, 'B')")


def test_attack_same_name_allowed_at_other_index(migrated) -> None:
    migrated.execute("INSERT INTO attacks (upgrade_id, attack_index, name) VALUES (1, 1, 'A')")


@pytest.mark.parametrize("column", NULLABLE_NUMBERS)
@pytest.mark.parametrize(("value", "valid"), [(None, True), (0, True), (2.5, True), (-1, False)])
def test_projectile_number_checks(migrated, column, value, valid) -> None:
    attempt(lambda: insert_projectile(migrated, **{column: value}), valid)


@pytest.mark.parametrize("column", ["unlimited_damage", "unlimited_pierce", "moab_only"])
@pytest.mark.parametrize(("value", "valid"), [(0, True), (1, True), (2, False), (-1, False)])
def test_projectile_flag_checks(migrated, column, value, valid) -> None:
    attempt(lambda: insert_projectile(migrated, **{column: value}), valid)


@pytest.mark.parametrize(("value", "valid"), [(0, True), (1, True), (2, False)])
def test_projectile_can_hit_camo_check(migrated, value, valid) -> None:
    attempt(lambda: insert_projectile(migrated, can_hit_camo=value), valid)


@pytest.mark.parametrize("flag", ["damage", "pierce"])
@pytest.mark.parametrize(
    ("flag_value", "number", "valid"),
    [(1, None, True), (1, 5, False), (1, 0, False), (0, 5, True), (0, None, True)],
)
def test_unlimited_flag_excludes_stored_number(migrated, flag, flag_value, number, valid) -> None:
    fields = {f"unlimited_{flag}": flag_value, flag: number}
    attempt(lambda: insert_projectile(migrated, **fields), valid)


def test_projectile_flags_are_independent(migrated) -> None:
    insert_projectile(migrated, unlimited_pierce=1, damage=0)


@pytest.mark.parametrize("column", ["name", "damage_type_id", "can_hit_camo"])
def test_projectile_required_columns(migrated, column) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_projectile(migrated, **{column: None})


def test_projectile_damage_type_must_exist(migrated) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_projectile(migrated, damage_type_id=999)


def test_projectile_attack_must_exist(migrated) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_projectile(migrated, attack_id=99)


def test_projectile_unique_per_attack_index(migrated) -> None:
    insert_projectile(migrated)
    with pytest.raises(sqlite3.IntegrityError):
        insert_projectile(migrated, name="Q")
    insert_projectile(migrated, projectile_index=1)


def test_projectile_index_check(migrated) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_projectile(migrated, projectile_index=-1)


def test_deleting_attack_deletes_projectiles(migrated) -> None:
    insert_projectile(migrated)
    migrated.execute("DELETE FROM attacks WHERE id = 1")
    assert migrated.execute("SELECT COUNT(*) FROM projectiles").fetchone()[0] == 0


def test_deleting_upgrade_deletes_attacks_and_projectiles(migrated) -> None:
    insert_projectile(migrated)
    migrated.execute("DELETE FROM upgrades WHERE id = 1")
    assert migrated.execute("SELECT COUNT(*) FROM attacks").fetchone()[0] == 0
    assert migrated.execute("SELECT COUNT(*) FROM projectiles").fetchone()[0] == 0


def test_deleting_tower_cascades_to_projectiles(migrated) -> None:
    insert_projectile(migrated)
    migrated.execute("DELETE FROM towers WHERE id = 1")
    assert migrated.execute("SELECT COUNT(*) FROM projectiles").fetchone()[0] == 0


def plan(connection: sqlite3.Connection, statement: str) -> str:
    steps = connection.execute("EXPLAIN QUERY PLAN " + statement)
    return " | ".join(row["detail"] for row in steps)


@pytest.fixture
def populated(migrated) -> sqlite3.Connection:
    for upgrade_id in range(2, 31):
        migrated.execute(
            "INSERT INTO upgrades (id, tower_id, path, damage_type_id, can_hit_camo)"
            " VALUES (?, 1, ?, 1, 1)",
            (upgrade_id, f"1-{upgrade_id // 6}-{upgrade_id % 6}"),
        )
    for attack_id in range(2, 60):
        migrated.execute(
            "INSERT INTO attacks (id, upgrade_id, attack_index, name) VALUES (?, ?, ?, 'A')",
            (attack_id, attack_id // 2 + 1, attack_id % 2),
        )
    migrated.executemany(
        "INSERT INTO projectiles (attack_id, projectile_index, name, damage_type_id,"
        " can_hit_camo) VALUES (?, ?, 'P', ?, 1)",
        [(attack, index, 1 + attack % 11) for attack in range(1, 60) for index in range(3)],
    )
    migrated.execute("ANALYZE")
    return migrated


def test_attacks_by_upgrade_uses_autoindex(populated) -> None:
    detail = plan(populated, "SELECT id FROM attacks WHERE upgrade_id = 3")
    assert "sqlite_autoindex_attacks_1" in detail


def test_projectiles_by_attack_uses_autoindex(populated) -> None:
    detail = plan(populated, "SELECT id FROM projectiles WHERE attack_id = 3")
    assert "sqlite_autoindex_projectiles_1" in detail


def test_projectiles_by_damage_type_uses_index(populated) -> None:
    detail = plan(populated, "SELECT id FROM projectiles WHERE damage_type_id = 3")
    assert "idx_projectiles_damage_type_id" in detail


def test_no_redundant_foreign_key_indexes(migrated) -> None:
    names = {row["name"] for row in migrated.execute("SELECT name FROM sqlite_master")}
    assert "idx_attacks_upgrade_id" not in names
    assert "idx_projectiles_attack_id" not in names
    assert "idx_projectiles_damage_type_id" in names
