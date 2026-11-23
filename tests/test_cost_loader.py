from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.costs import total_cost
from btd6.db import connect
from btd6.db.cost_loader import load_costs
from btd6.db.loader import load_tower
from btd6.db.seed import initialize_database
from btd6.etl import fetch
from btd6.etl.pipeline import refresh_database
from tests.factories import CostsFactory, UpgradeCostRowFactory

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURE_PATH = FIXTURE_DIR / "costs_super_monkey_cargo.json"


@pytest.fixture
def cargo_costs(offline_costs_wiki: None) -> dict[str, Any]:
    return fetch.fetch_costs("Super Monkey")


def cost_rows(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    query = (
        "SELECT t.name, c.path_index, c.tier, c.name, c.cost FROM upgrade_costs c "
        "JOIN towers t ON t.id = c.tower_id ORDER BY 1, 2, 3"
    )
    return [tuple(row) for row in connection.execute(query)]


def base_cost(connection: sqlite3.Connection, tower_name: str) -> int | None:
    cursor = connection.execute("SELECT base_cost FROM towers WHERE name = ?", (tower_name,))
    return cursor.fetchone()[0]


def insert_cost_sql(values: str) -> str:
    return (
        "INSERT INTO upgrade_costs (tower_id, path_index, tier, name, cost) "
        f"SELECT id, {values} FROM towers"
    )


def test_migration_adds_cost_schema(database: sqlite3.Connection) -> None:
    tower_columns = {row[1] for row in database.execute("PRAGMA table_info(towers)")}
    cost_columns = {row[1] for row in database.execute("PRAGMA table_info(upgrade_costs)")}
    assert "base_cost" in tower_columns
    assert {"id", "tower_id", "path_index", "tier", "name", "cost"} <= cost_columns


def test_migration_file_is_numbered_002() -> None:
    migrations = Path(__file__).parents[1] / "btd6" / "db" / "migrations"
    assert (migrations / "002_costs.sql").exists()


def test_load_costs_stores_base_cost_and_all_upgrades(
    database: sqlite3.Connection, cargo_costs: dict[str, Any]
) -> None:
    load_costs(database, "Super Monkey", cargo_costs)
    assert base_cost(database, "Super Monkey") == 2500
    assert len(cost_rows(database)) == 15
    assert ("Super Monkey", 1, 1, "Laser Blasts", 2000) in cost_rows(database)


def test_load_costs_creates_missing_tower_with_category(database: sqlite3.Connection) -> None:
    load_costs(database, "Wizard Monkey", CostsFactory.build(base_cost=400))
    cursor = database.execute("SELECT category FROM towers WHERE name = 'Wizard Monkey'")
    assert cursor.fetchone()[0] == "Magic"


def test_load_costs_keeps_existing_upgrades(
    database: sqlite3.Connection, super_monkey_resolved: dict[str, Any], cargo_costs: dict[str, Any]
) -> None:
    load_tower(database, "Super Monkey", super_monkey_resolved)
    load_costs(database, "Super Monkey", cargo_costs)
    assert database.execute("SELECT COUNT(*) FROM upgrades").fetchone()[0] == 64


def test_load_costs_twice_does_not_duplicate(
    database: sqlite3.Connection, cargo_costs: dict[str, Any]
) -> None:
    load_costs(database, "Super Monkey", cargo_costs)
    first = cost_rows(database)
    load_costs(database, "Super Monkey", cargo_costs)
    assert cost_rows(database) == first
    assert database.execute("SELECT COUNT(*) FROM towers").fetchone()[0] == 1


def test_load_costs_replaces_changed_prices(database: sqlite3.Connection) -> None:
    load_costs(database, "Wizard Monkey", CostsFactory.build(base_cost=400))
    updated = CostsFactory.build(base_cost=450, upgrades=[UpgradeCostRowFactory.build(cost=999)])
    load_costs(database, "Wizard Monkey", updated)
    assert base_cost(database, "Wizard Monkey") == 450
    assert [row[4] for row in cost_rows(database)] == [999]


def test_load_costs_leaves_other_towers_alone(database: sqlite3.Connection) -> None:
    load_costs(database, "Wizard Monkey", CostsFactory.build(base_cost=400))
    load_costs(database, "Ninja Monkey", CostsFactory.build(base_cost=500))
    load_costs(database, "Wizard Monkey", CostsFactory.build(base_cost=410))
    assert base_cost(database, "Ninja Monkey") == 500
    assert len([row for row in cost_rows(database) if row[0] == "Ninja Monkey"]) == 15


@pytest.mark.parametrize(
    ("bad_field", "bad_value"), [("path", 4), ("path", 0), ("tier", 6), ("tier", 0)]
)
def test_load_costs_rolls_back_on_invalid_row(
    database: sqlite3.Connection, bad_field: str, bad_value: int
) -> None:
    load_costs(database, "Wizard Monkey", CostsFactory.build(base_cost=400))
    before = cost_rows(database)
    bad = CostsFactory.build(base_cost=999)
    bad["upgrades"].append(UpgradeCostRowFactory.build(**{bad_field: bad_value}))
    with pytest.raises(sqlite3.IntegrityError):
        load_costs(database, "Wizard Monkey", bad)
    assert cost_rows(database) == before
    assert base_cost(database, "Wizard Monkey") == 400


def test_load_costs_rolls_back_new_tower_on_failure(database: sqlite3.Connection) -> None:
    bad = CostsFactory.build()
    bad["upgrades"].append(UpgradeCostRowFactory.build(tier=9))
    with pytest.raises(sqlite3.IntegrityError):
        load_costs(database, "Wizard Monkey", bad)
    assert database.execute("SELECT COUNT(*) FROM towers").fetchone()[0] == 0


def test_load_costs_rejects_duplicate_slot_in_one_payload(database: sqlite3.Connection) -> None:
    duplicated = CostsFactory.build()
    duplicated["upgrades"].append(UpgradeCostRowFactory.build(path=1, tier=1))
    with pytest.raises(sqlite3.IntegrityError):
        load_costs(database, "Wizard Monkey", duplicated)


def test_schema_enforces_unique_slot(database: sqlite3.Connection) -> None:
    load_costs(database, "Wizard Monkey", CostsFactory.build())
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(insert_cost_sql("1, 1, 'dup', 1"))


def test_schema_rejects_null_cost(database: sqlite3.Connection) -> None:
    load_costs(database, "Wizard Monkey", CostsFactory.build())
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(insert_cost_sql("1, 1, 'x', NULL"))


def test_schema_rejects_orphan_cost_row(database: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO upgrade_costs (tower_id, path_index, tier, name, cost) "
            "VALUES (9999, 1, 1, 'orphan', 1)"
        )


@settings(deadline=None, max_examples=25)
@given(
    base=st.integers(min_value=0, max_value=10**6),
    prices=st.lists(st.integers(min_value=0, max_value=10**6), min_size=15, max_size=15),
)
def test_load_costs_idempotent_property(base: int, prices: list[int]) -> None:
    connection = connect(":memory:")
    initialize_database(connection)
    costs = CostsFactory.build(base_cost=base)
    for row, price in zip(costs["upgrades"], prices, strict=True):
        row["cost"] = price
    load_costs(connection, "Wizard Monkey", costs)
    first = cost_rows(connection)
    load_costs(connection, "Wizard Monkey", costs)
    assert cost_rows(connection) == first
    assert len(first) == 15
    connection.close()


def test_refresh_database_stores_costs(
    database: sqlite3.Connection, cargo_costs: dict[str, Any]
) -> None:
    resolved = json.loads((FIXTURE_DIR / "super_monkey_resolved.json").read_text())
    refresh_database(database, ["Super Monkey"], fetch=lambda _name: resolved)
    assert base_cost(database, "Super Monkey") == 2500
    assert len(cost_rows(database)) == 15


def test_round_trip_fixture_to_total_cost(
    database: sqlite3.Connection, cargo_costs: dict[str, Any]
) -> None:
    load_costs(database, "Super Monkey", cargo_costs)
    assert total_cost(database, "Super Monkey", "0-0-0") == 2500
    load_costs(database, "Super Monkey", cargo_costs)
    assert total_cost(database, "Super Monkey", "0-0-0") == 2500
    assert len(cost_rows(database)) == 15
