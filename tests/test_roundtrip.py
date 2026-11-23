from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from btd6.db.loader import load_tower
from btd6.db.round_loader import load_bloons, load_rounds
from btd6.etl.extract import extract_bloon_rows, extract_round_rows
from btd6.etl.fetch import normalize_cargo_keys

COLUMNS = [
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
]
JOINED_QUERY = (
    "SELECT u.path, "
    + ", ".join(f"u.{column}" for column in COLUMNS)
    + ", d.name AS damage_type FROM upgrades u "
    "JOIN damage_types d ON d.id = u.damage_type_id ORDER BY u.path"
)


def normalize(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if value is not None and pd.isna(value):
        return None
    return value


def golden_rows(golden_csv_path: Any) -> dict[str, dict[str, Any]]:
    frame = pd.read_csv(golden_csv_path).set_index("path")
    return {
        path: {
            column: normalize(value.item() if hasattr(value, "item") else value)
            for column, value in row.items()
        }
        for path, row in frame.iterrows()
    }


def database_rows(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {
        row["path"]: {key: row[key] for key in row.keys() if key != "path"}
        for row in connection.execute(JOINED_QUERY)
    }


def differing_cells(
    golden: dict[str, dict[str, Any]], stored: dict[str, dict[str, Any]]
) -> list[tuple[str, str]]:
    if golden.keys() != stored.keys():
        return [("<paths>", "<paths>")]
    return [
        (path, column)
        for path, row in golden.items()
        for column in COLUMNS + ["damage_type"]
        if row[column] != stored[path][column]
    ]


def test_loaded_database_matches_golden_csv(
    database: sqlite3.Connection, super_monkey_resolved: dict[str, Any], golden_csv_path: Any
) -> None:
    load_tower(database, "Super Monkey", super_monkey_resolved)
    golden = golden_rows(golden_csv_path)
    assert len(golden) == 64
    assert differing_cells(golden, database_rows(database)) == []


def test_mutated_fixture_value_is_detected(
    database: sqlite3.Connection, super_monkey_resolved: dict[str, Any], golden_csv_path: Any
) -> None:
    mutated = copy.deepcopy(super_monkey_resolved)
    mutated["_100"]["range"] += 1
    load_tower(database, "Super Monkey", mutated)
    differences = differing_cells(golden_rows(golden_csv_path), database_rows(database))
    assert differences == [("1-0-0", "range")]


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_roundset_fixture_loads_and_reads_back_as_csv_rows(database: sqlite3.Connection) -> None:
    raw_bloons = [
        normalize_cargo_keys(entry["title"])
        for entry in json.loads((FIXTURE_DIR / "bloons_cargo_response.json").read_text())[
            "cargoquery"
        ]
    ]
    roundset = json.loads((FIXTURE_DIR / "default_roundset_first10.json").read_text())
    rows = extract_round_rows(roundset)
    load_bloons(database, extract_bloon_rows(raw_bloons))
    ids = {row[0]: row[1] for row in database.execute("SELECT name, id FROM bloons")}
    assert load_rounds(database, rows, ids) == len(rows)
    stored = database.execute(
        "SELECT round, group_index, bloons.name AS bloon, count, start, duration "
        "FROM round_groups JOIN bloons ON bloons.id = bloon_id ORDER BY round, group_index"
    ).fetchall()
    expected = pd.read_csv(FIXTURE_DIR / "default_roundset_first10_rows.csv")
    assert [tuple(row) for row in stored] == list(expected.itertuples(index=False, name=None))
