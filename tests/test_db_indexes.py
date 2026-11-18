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
    connection.execute("INSERT INTO towers VALUES (1, 'Super Monkey', 'Magic')")
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
