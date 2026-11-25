from __future__ import annotations

import dataclasses
import json
import math
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy

from btd6.agent.schemas import TOOL_SCHEMAS as TOOL_SCHEMAS
from btd6.costs import total_cost
from btd6.game_state import load_game_state, state_summary
from btd6.query import QueryError, UpgradeFilters, search_upgrades
from btd6.ranking import rank_upgrades
from btd6.recommend import DEFAULT_HORIZON, parse_owned
from btd6.recommend import recommend as recommend_upgrades
from btd6.rounds import NoRoundDataError
from btd6.threats import round_threats

RANK_KEYS = (
    "tower_name",
    "path",
    "total_cost",
    "dps",
    "moab_dps",
    "pierce_weighted_dps",
    "damage_per_dollar",
    "pierce_damage_per_dollar",
    "projectile_pierce",
    "can_hit_camo",
)
ERROR_TYPES = (QueryError, NoRoundDataError, ValueError, TypeError, sqlite3.Error)


def plain(value: object) -> object:
    if isinstance(value, numpy.generic):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]
    return value


def dataclass_to_plain(value: object) -> object:
    return plain(dataclasses.asdict(value))


def clean_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned = plain(row)
    for key, value in cleaned.items():
        if key.startswith("can_") and value is not None:
            cleaned[key] = bool(value)
    return cleaned


def get_round_threats(
    connection: sqlite3.Connection,
    round: int,  # noqa: A002
) -> dict[str, Any]:
    return dataclass_to_plain(round_threats(connection, round))


def search_upgrades_tool(
    connection: sqlite3.Connection,
    sort_by: str | None = None,
    descending: bool = True,
    limit: int = 10,
    **filter_values: object,
) -> dict[str, Any]:
    rows = search_upgrades(connection, UpgradeFilters(**filter_values), sort_by, descending, limit)
    return {"upgrades": [clean_row(dict(row)) for row in rows]}


def rank_upgrades_tool(
    connection: sqlite3.Connection,
    filters: dict[str, Any] | None = None,
    metric: str = "damage_per_dollar",
    difficulty: str = "medium",
    limit: int = 10,
) -> dict[str, Any]:
    frame = rank_upgrades(connection, UpgradeFilters(**(filters or {})), metric, difficulty, limit)
    rows = [clean_row({key: row[key] for key in RANK_KEYS}) for row in frame.to_dict("records")]
    for row in rows:
        if row["total_cost"] is not None:
            row["total_cost"] = int(row["total_cost"])
    return {"upgrades": rows}


def recommend_tool(
    connection: sqlite3.Connection,
    round: int,  # noqa: A002
    money: int,
    difficulty: str = "medium",
    limit: int = 5,
    horizon: int = DEFAULT_HORIZON,
    one_per_tower: bool = False,
    owned: list[str] | None = None,
) -> dict[str, Any]:
    towers = [parse_owned(text) for text in owned or []]
    results = recommend_upgrades(
        connection, round, money, difficulty, limit, horizon, towers, one_per_tower
    )
    return {"recommendations": [dataclass_to_plain(result) for result in results]}


def total_cost_tool(
    connection: sqlite3.Connection, tower_name: str, path: str, difficulty: str = "medium"
) -> dict[str, Any]:
    cost = total_cost(connection, tower_name, path, difficulty)
    return {"tower_name": tower_name, "path": path, "difficulty": difficulty, "total_cost": cost}


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_round_threats": get_round_threats,
    "search_upgrades": search_upgrades_tool,
    "rank_upgrades": rank_upgrades_tool,
    "recommend": recommend_tool,
    "total_cost": total_cost_tool,
}


def error_result(error_type: str, message: str) -> dict[str, Any]:
    return {"error": {"type": error_type, "message": message}}


NOT_LIVE_MESSAGE = "No live game in this run. Start the agent with --live to read the game state."


def get_game_state_tool(state_path: Path) -> dict[str, Any]:
    current_time = datetime.now(UTC)
    return state_summary(load_game_state(state_path, now=current_time), current_time)


def run_game_state_tool(state_path: Path | None, arguments: dict[str, Any]) -> dict:
    if state_path is None:
        return error_result("LiveStateUnavailable", NOT_LIVE_MESSAGE)
    try:
        return get_game_state_tool(state_path, **arguments)
    except ERROR_TYPES as error:
        return error_result(type(error).__name__, str(error))


def call_tool(
    connection: sqlite3.Connection,
    name: str,
    arguments: dict[str, Any],
    state_path: Path | None = None,
) -> dict:
    if name == "get_game_state":
        return run_game_state_tool(state_path, arguments)
    tool = TOOLS.get(name)
    if tool is None:
        return error_result("UnknownTool", f"Unknown tool: {name!r}")
    try:
        return tool(connection, **arguments)
    except ERROR_TYPES as error:
        return error_result(type(error).__name__, str(error))


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict
    result: dict


def decode_arguments(raw: str) -> dict | None:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def execute_call(
    connection: sqlite3.Connection, call: Mapping[str, Any], state_path: Path | None = None
) -> ToolCall:
    name = call["function"]["name"]
    arguments = decode_arguments(call["function"]["arguments"])
    if arguments is None:
        return ToolCall(name, {}, error_result("ArgumentError", "Arguments must be a JSON object"))
    return ToolCall(name, arguments, call_tool(connection, name, arguments, state_path))
