from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from btd6.db import connect
from btd6.db.seed import initialize_database
from tests.recommend_fixture import build_recommend_database

SCENARIO_FILE = Path(__file__).parent / "scenarios.json"


def load_scenarios(live_only: bool = False) -> list[dict[str, Any]]:
    scenarios = json.loads(SCENARIO_FILE.read_text())
    if live_only:
        return [scenario for scenario in scenarios if scenario["live"]]
    return scenarios


def build_offline_connection(scenario: dict[str, Any]) -> sqlite3.Connection:
    return build_recommend_database(with_rounds=scenario["database"] != "no_rounds")


def build_live_connection(scenario: dict[str, Any], database_path: Path) -> sqlite3.Connection:
    if scenario["database"] == "no_rounds":
        connection = connect(":memory:")
        initialize_database(connection)
        return connection
    return connect(str(database_path))
