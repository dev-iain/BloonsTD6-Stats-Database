from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from btd6.db import apply_migrations, connect
from btd6.db.round_loader import load_bloons, load_income, load_rounds

FIXTURES = Path(__file__).parent / "fixtures"


def read_group_rows(max_round: int) -> list[dict[str, Any]]:
    with (FIXTURES / "roundset_rows_1_100.csv").open(newline="") as handle:
        rows = [
            {
                "round": int(row["round"]),
                "group_index": int(row["group_index"]),
                "bloon": row["bloon"],
                "count": int(row["count"]),
                "start": float(row["start"]),
                "duration": float(row["duration"]),
            }
            for row in csv.DictReader(handle)
        ]
    return [row for row in rows if row["round"] <= max_round]


def build_connection(max_round: int | None, with_income: bool = True) -> sqlite3.Connection:
    connection = connect(":memory:")
    apply_migrations(connection)
    load_bloons(connection, json.loads((FIXTURES / "bloon_rows.json").read_text()))
    if with_income:
        load_income(connection, json.loads((FIXTURES / "default_income_set.json").read_text()))
    if max_round is not None:
        bloon_ids = {
            row["name"]: row["id"] for row in connection.execute("SELECT id, name FROM bloons")
        }
        load_rounds(connection, read_group_rows(max_round), bloon_ids)
    return connection


def save_connection(source: sqlite3.Connection, path: Path) -> str:
    target = connect(str(path))
    source.backup(target)
    target.close()
    return str(path)
