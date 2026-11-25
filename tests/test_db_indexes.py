from __future__ import annotations

import pytest

from btd6.db import apply_migrations, connect

PLAN_QUERIES = {
    "idx_upgrades_projectile_pierce": "SELECT id FROM upgrades WHERE projectile_pierce >= 5",
    "idx_upgrades_projectile_damage": "SELECT id FROM upgrades WHERE projectile_damage >= 5",
    "idx_upgrades_range": "SELECT id FROM upgrades WHERE range >= 50",
    "idx_upgrades_damage_type_id": "SELECT id FROM upgrades WHERE damage_type_id = 3",
    "sqlite_autoindex_upgrades_1": "SELECT id FROM upgrades WHERE tower_id = 1 AND path = '0-0-0'",
}


@pytest.fixture(scope="module")
def populated_connection():
    connection = connect(":memory:")
    apply_migrations(connection)
    connection.execute(
        "INSERT INTO towers (id, name, category) VALUES (1, 'Super Monkey', 'Magic')"
    )
    rows = [
        (1, f"{first}-{second}-0", 1 + (first + second) % 11, first * 10, first + second, first, 1)
        for first in range(6)
        for second in range(6)
    ]
    connection.executemany(
        "INSERT INTO upgrades (tower_id, path, damage_type_id, range, projectile_pierce,"
        " projectile_damage, can_hit_camo) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    connection.execute("ANALYZE")
    yield connection
    connection.close()


def plan_details(connection, sql: str) -> str:
    return " | ".join(row["detail"] for row in connection.execute("EXPLAIN QUERY PLAN " + sql))


@pytest.mark.parametrize(("index_name", "sql"), PLAN_QUERIES.items())
def test_filter_uses_index(populated_connection, index_name, sql):
    detail = plan_details(populated_connection, sql)
    assert "SEARCH upgrades USING" in detail
    assert index_name in detail


def test_camo_filter_scans(populated_connection):
    detail = plan_details(populated_connection, "SELECT id FROM upgrades WHERE can_hit_camo = 1")
    assert "SCAN upgrades" in detail


def test_round_groups_round_filter_uses_index(populated_connection):
    populated_connection.execute("INSERT INTO bloons (id, name, is_moab) VALUES (1, 'Red', 0)")
    for round_number in range(1, 41):
        populated_connection.execute("INSERT INTO rounds (round) VALUES (?)", (round_number,))
        populated_connection.execute(
            "INSERT INTO round_groups (round, group_index, bloon_id, is_camo, is_regrow,"
            " is_fortified, count, start, duration) VALUES (?, 0, 1, 0, 0, 0, 10, 0, 5)",
            (round_number,),
        )
    populated_connection.execute("ANALYZE")
    detail = plan_details(populated_connection, "SELECT id FROM round_groups WHERE round = 12")
    assert "SEARCH round_groups USING" in detail
    assert "idx_round_groups_round" in detail or "sqlite_autoindex_round_groups" in detail


def test_round_groups_bloon_id_filter_uses_index(populated_connection):
    detail = plan_details(populated_connection, "SELECT id FROM round_groups WHERE bloon_id = 1")
    assert "idx_round_groups_bloon_id" in detail


def test_effects_by_projectile_uses_autoindex(populated_connection):
    populated_connection.execute(
        "INSERT INTO attacks (id, upgrade_id, attack_index, name) VALUES (1, 1, 0, 'A')"
    )
    populated_connection.executemany(
        "INSERT INTO projectiles (id, attack_id, projectile_index, name, damage_type_id,"
        " can_hit_camo) VALUES (?, 1, ?, 'P', 1, 1)",
        [(number, number - 1) for number in range(1, 31)],
    )
    populated_connection.executemany(
        "INSERT INTO projectile_effects (projectile_id, effect_index, name, damage,"
        " tick_interval, lifespan, trigger_immediate, damage_type_id)"
        " VALUES (?, ?, 'E', 1, 1, 1, 0, 1)",
        [(projectile, index) for projectile in range(1, 31) for index in range(3)],
    )
    populated_connection.execute("ANALYZE")
    detail = plan_details(
        populated_connection, "SELECT id FROM projectile_effects WHERE projectile_id = 3"
    )
    assert "sqlite_autoindex_projectile_effects_1" in detail


def test_effects_by_damage_type_uses_index(populated_connection):
    detail = plan_details(
        populated_connection, "SELECT id FROM projectile_effects WHERE damage_type_id = 3"
    )
    assert "idx_projectile_effects_damage_type_id" in detail
