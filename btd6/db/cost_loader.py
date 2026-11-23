from __future__ import annotations

import sqlite3
from typing import Any

from btd6.db.loader import ensure_tower

INSERT_COST_SQL = (
    "INSERT INTO upgrade_costs (tower_id, path_index, tier, name, cost) VALUES (?, ?, ?, ?, ?)"
)


def load_costs(connection: sqlite3.Connection, tower_name: str, costs: dict[str, Any]) -> int:
    """Replace one tower's base cost and upgrade costs in a single transaction.

    Returns the number of upgrade cost rows written.
    """
    with connection:
        tower_id = ensure_tower(connection, tower_name, costs["category"])
        connection.execute(
            "UPDATE towers SET base_cost = ? WHERE id = ?", (costs["base_cost"], tower_id)
        )
        connection.execute("DELETE FROM upgrade_costs WHERE tower_id = ?", (tower_id,))
        connection.executemany(
            INSERT_COST_SQL,
            [
                (tower_id, row["path"], row["tier"], row["name"], row["cost"])
                for row in costs["upgrades"]
            ],
        )
    return len(costs["upgrades"])
