from __future__ import annotations

import sqlite3
from typing import Any

from btd6.etl.extract import extract_attack_rows, extract_row

UPGRADE_COLUMNS = (
    "path",
    "range",
    "footprint_radius",
    "attack_rate",
    "projectile_count",
    "projectile_damage",
    "projectile_pierce",
    "projectile_speed",
    "projectile_radius",
    "projectile_lifespan",
    "can_hit_camo",
    "ability_cooldown",
)
INSERT_UPGRADE_SQL = (
    "INSERT INTO upgrades (tower_id, damage_type_id, "
    + ", ".join(UPGRADE_COLUMNS)
    + ") VALUES (?, ?, "
    + ", ".join("?" * len(UPGRADE_COLUMNS))
    + ")"
)


def ensure_tower(connection: sqlite3.Connection, name: str, category: str) -> int:
    """Return the id of the tower called `name`, inserting it first if missing."""
    connection.execute(
        "INSERT INTO towers (name, category) VALUES (?, ?) ON CONFLICT (name) DO NOTHING",
        (name, category),
    )
    row = connection.execute("SELECT id FROM towers WHERE name = ?", (name,)).fetchone()
    return int(row[0])


def damage_type_ids(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute("SELECT name, id FROM damage_types")
    return {row[0]: row[1] for row in rows}


def upgrade_params(
    tower_id: int, type_ids: dict[str, int], code: str, stats: dict[str, Any]
) -> tuple[Any, ...]:
    row = extract_row(code, stats)
    type_id = type_ids.get(row["damage_type"], type_ids["Unknown"])
    values = [int(row[key]) if isinstance(row[key], bool) else row[key] for key in UPGRADE_COLUMNS]
    return (tower_id, type_id, *values)


PROJECTILE_COLUMNS = (
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
)
INSERT_PROJECTILE_SQL = (
    "INSERT INTO projectiles (attack_id, damage_type_id, can_hit_camo, "
    + ", ".join(PROJECTILE_COLUMNS)
    + ") VALUES (?, ?, ?, "
    + ", ".join("?" * len(PROJECTILE_COLUMNS))
    + ")"
)


def insert_attacks(
    connection: sqlite3.Connection, upgrade_id: int, type_ids: dict[str, int], stats: dict[str, Any]
) -> None:
    for attack in extract_attack_rows(stats):
        cursor = connection.execute(
            "INSERT INTO attacks (upgrade_id, attack_index, name, rate) VALUES (?, ?, ?, ?)",
            (upgrade_id, attack["attack_index"], attack["name"], attack["rate"]),
        )
        for projectile in attack["projectiles"]:
            type_id = type_ids.get(projectile["damage_type"], type_ids["Unknown"])
            values = [
                int(projectile[key]) if isinstance(projectile[key], bool) else projectile[key]
                for key in PROJECTILE_COLUMNS
            ]
            connection.execute(
                INSERT_PROJECTILE_SQL,
                (cursor.lastrowid, type_id, int(projectile["can_hit_camo"]), *values),
            )


def insert_upgrade(
    connection: sqlite3.Connection,
    tower_id: int,
    type_ids: dict[str, int],
    code: str,
    stats: dict[str, Any],
) -> None:
    cursor = connection.execute(INSERT_UPGRADE_SQL, upgrade_params(tower_id, type_ids, code, stats))
    insert_attacks(connection, cursor.lastrowid, type_ids, stats)


def load_tower(
    connection: sqlite3.Connection,
    tower_name: str,
    resolved: dict[str, dict[str, Any]],
    category: str = "Magic",
) -> int:
    """Replace one tower's upgrades with `resolved` in a single transaction.

    Upgrades missing from the new data are deleted; other towers are untouched.
    Any failure rolls back everything, including a newly created tower row.
    Returns the number of upgrades written.
    """
    with connection:
        tower_id = ensure_tower(connection, tower_name, category)
        type_ids = damage_type_ids(connection)
        connection.execute("DELETE FROM upgrades WHERE tower_id = ?", (tower_id,))
        for code, stats in resolved.items():
            insert_upgrade(connection, tower_id, type_ids, code, stats)
    return len(resolved)
