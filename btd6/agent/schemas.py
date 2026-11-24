from __future__ import annotations

from typing import Any

from btd6.costs import DIFFICULTY_MULTIPLIERS
from btd6.query import SORT_COLUMNS
from btd6.ranking import METRICS

DIFFICULTIES = list(DIFFICULTY_MULTIPLIERS)
BOOLEAN = {"type": "boolean"}
NUMBER = {"type": "number", "minimum": 0}
ROUND = {"type": "integer", "minimum": 1, "maximum": 100}
DIFFICULTY = {"type": "string", "enum": DIFFICULTIES, "default": "medium"}


def limit_schema(default: int) -> dict[str, Any]:
    return {"type": "integer", "minimum": 1, "maximum": 50, "default": default}


FILTER_PROPERTIES: dict[str, Any] = {
    "tower_name": {"type": "string", "description": 'Exact tower name, e.g. "Super Monkey"'},
    "tower_name_contains": {"type": "string"},
    "category": {"type": "string", "description": 'Tower category, e.g. "Magic"'},
    **{
        f"can_pop_{name}": BOOLEAN
        for name in ("lead", "black", "white", "purple", "glass", "frozen")
    },
    "can_hit_camo": BOOLEAN,
    "min_range": NUMBER,
    "min_pierce": NUMBER,
    "min_damage": NUMBER,
    "min_projectile_speed": NUMBER,
    "damage_type": {"type": "string", "description": 'Damage type name, e.g. "Normal", "Plasma"'},
}


def function_schema(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    parameters: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        parameters["required"] = required
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    function_schema(
        "get_round_threats",
        "What a round contains: total RBE (red bloon equivalent) and the share of RBE that is "
        "camo, regrow, MOAB-class and each pop property (lead, black, white, purple, glass, "
        "frozen). Call this first.",
        {"round": ROUND},
        ["round"],
    ),
    function_schema(
        "search_upgrades",
        "Find upgrades by stats. Filters combine with AND. "
        "Returns raw stats of each upgrade's main attack.",
        {
            **FILTER_PROPERTIES,
            "sort_by": {"type": "string", "enum": list(SORT_COLUMNS)},
            "descending": {**BOOLEAN, "default": True},
            "limit": limit_schema(10),
        },
        [],
    ),
    function_schema(
        "rank_upgrades",
        "Rank upgrades by a derived metric (dps, moab_dps, damage_per_dollar, "
        "pierce_damage_per_dollar) with difficulty-adjusted total cost.",
        {
            "filters": {"type": "object", "properties": FILTER_PROPERTIES},
            "metric": {"type": "string", "enum": list(METRICS), "default": "damage_per_dollar"},
            "difficulty": DIFFICULTY,
            "limit": limit_schema(10),
        },
        [],
    ),
    function_schema(
        "recommend",
        "Affordable upgrades that can pop everything the round contains (camo, lead, ...), "
        "ranked by round-fit score per dollar. Reasons explain each match.",
        {
            "round": ROUND,
            "money": {"type": "integer", "minimum": 0},
            "difficulty": DIFFICULTY,
            "limit": limit_schema(5),
        },
        ["round", "money"],
    ),
    function_schema(
        "total_cost",
        "Total cost (base plus every tier on the path) of an upgrade at a difficulty.",
        {
            "tower_name": {"type": "string"},
            "path": {"type": "string", "pattern": "^[0-5]-[0-5]-[0-5]$"},
            "difficulty": DIFFICULTY,
        },
        ["tower_name", "path"],
    ),
]

GAME_STATE_SCHEMA = function_schema(
    "get_game_state",
    "The live game as the mod last reported it: round, cash (money), lives, difficulty, map "
    "and the towers already placed (tower_name, path X-Y-Z; known is false for towers that are "
    "not in the database). Call it when cash or towers may have changed.",
    {},
    [],
)
LIVE_TOOL_SCHEMAS: list[dict[str, Any]] = [*TOOL_SCHEMAS, GAME_STATE_SCHEMA]
