from __future__ import annotations

import json
import sqlite3
from typing import Any

from btd6.db import connect
from btd6.db.cost_loader import load_costs
from btd6.db.loader import load_tower
from btd6.db.round_loader import load_bloons, load_rounds
from btd6.db.seed import initialize_database
from btd6.etl.fetch import fetch_costs
from tests.income_fixture import FIXTURES, read_group_rows
from tests.test_ranking import UPGRADE_STATS, build_database

CAMO_ROUND = 101
CAMO_PATHS = {"0-0-4"}
RESOLVED_TOWER_FILES = {
    "Super Monkey": "super_monkey_resolved.json",
    "Alchemist": "alchemist_resolved.json",
    "Druid": "druid_resolved.json",
    "Ninja Monkey": "ninja_resolved.json",
    "Wizard Monkey": "wizard_resolved.json",
    "Dart Monkey": "dart_monkey_resolved_sample.json",
    "Boomerang Monkey": "boomerang_monkey_resolved_sample.json",
    "Bomb Shooter": "bomb_shooter_resolved_sample.json",
    "Sniper Monkey": "sniper_monkey_resolved_sample.json",
    "Ice Monkey": "ice_monkey_resolved_sample.json",
}
MAGIC_TOWERS = {"Super Monkey", "Alchemist", "Druid", "Ninja Monkey", "Wizard Monkey"}


def camo_specs() -> dict[str, dict[str, Any]]:
    return {
        path: {**stats, "can_hit_camo": path in CAMO_PATHS} for path, stats in UPGRADE_STATS.items()
    }


def load_round_data(connection: sqlite3.Connection, with_camo_round: bool = True) -> None:
    load_bloons(connection, json.loads((FIXTURES / "bloon_rows.json").read_text()))
    connection.execute("UPDATE bloons SET has_lead = 1 WHERE name = 'Lead'")
    connection.commit()
    rows = read_group_rows(100)
    if with_camo_round:
        rows.append(
            {
                "round": CAMO_ROUND,
                "group_index": 0,
                "bloon": "BlueCamo",
                "count": 10,
                "start": 0.0,
                "duration": 1.0,
            }
        )
    bloon_ids = {
        row["name"]: row["id"] for row in connection.execute("SELECT id, name FROM bloons")
    }
    load_rounds(connection, rows, bloon_ids)


def build_recommend_database(
    with_costs: bool = True, with_rounds: bool = True
) -> sqlite3.Connection:
    """Four-upgrade Super Monkey database; only `0-0-4` hits camo."""
    connection = build_database(camo_specs(), with_costs=with_costs)
    if with_rounds:
        load_round_data(connection)
    return connection


def build_full_database(rounds: bool = True) -> sqlite3.Connection:
    """Every resolved tower fixture, Super Monkey costs for each, rounds 1-100.

    The caller must use the `offline_costs_wiki` fixture.
    """
    connection = connect(":memory:")
    initialize_database(connection)
    for name, file_name in RESOLVED_TOWER_FILES.items():
        resolved = json.loads((FIXTURES / file_name).read_text())
        category = "Magic" if name in MAGIC_TOWERS else "Primary"
        load_tower(connection, name, resolved, category)
        load_costs(connection, name, fetch_costs(name))
    if rounds:
        load_round_data(connection, with_camo_round=False)
    return connection
