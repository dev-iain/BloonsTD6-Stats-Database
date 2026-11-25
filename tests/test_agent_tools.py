from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from btd6.agent.tools import RANK_KEYS, TOOL_SCHEMAS, call_tool
from btd6.costs import DIFFICULTY_MULTIPLIERS
from btd6.ranking import METRICS
from tests.recommend_fixture import build_recommend_database

TOOL_NAMES = [
    "get_round_threats",
    "search_upgrades",
    "rank_upgrades",
    "recommend",
    "total_cost",
]
REQUIRED = {
    "get_round_threats": ["round"],
    "search_upgrades": [],
    "rank_upgrades": [],
    "recommend": ["round", "money"],
    "total_cost": ["tower_name", "path"],
}
VALID_ARGUMENTS: dict[str, dict[str, Any]] = {
    "get_round_threats": {"round": 63},
    "search_upgrades": {"tower_name": "Super Monkey", "can_hit_camo": True, "limit": 1},
    "rank_upgrades": {"filters": {"tower_name": "Super Monkey"}, "metric": "dps", "limit": 2},
    "recommend": {"round": 63, "money": 100000, "horizon": 1},
    "total_cost": {"tower_name": "Super Monkey", "path": "1-0-0"},
}
FILTER_NAMES = {
    "tower_name",
    "tower_name_contains",
    "category",
    "can_pop_lead",
    "can_pop_black",
    "can_pop_white",
    "can_pop_purple",
    "can_pop_glass",
    "can_pop_frozen",
    "can_hit_camo",
    "min_range",
    "min_pierce",
    "min_damage",
    "min_projectile_speed",
    "damage_type",
}
SEARCH_KEYS = {
    "tower_name",
    "category",
    "path",
    "range",
    "attack_rate",
    "projectile_count",
    "projectile_damage",
    "projectile_pierce",
    "projectile_speed",
    "projectile_radius",
    "projectile_lifespan",
    "footprint_radius",
    "can_hit_camo",
    "ability_cooldown",
    "damage_type",
    "can_pop_lead",
    "can_pop_black",
    "can_pop_white",
    "can_pop_purple",
    "can_pop_glass",
    "can_pop_frozen",
}
FLAG_KEYS = sorted(key for key in SEARCH_KEYS if key.startswith("can_"))
RECOMMENDATION_KEYS = {
    "tower_name",
    "path",
    "total_cost",
    "upgrade_from",
    "score",
    "dps",
    "moab_dps",
    "pierce_weighted_dps",
    "projectile_pierce",
    "effective_pierce",
    "first_leak_round",
    "reasons",
}


@pytest.fixture
def tool_database() -> Iterator[sqlite3.Connection]:
    connection = build_recommend_database()
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def shared_database() -> Iterator[sqlite3.Connection]:
    connection = build_recommend_database()
    yield connection
    connection.close()


@pytest.fixture
def database_factory() -> Iterator[Callable[..., sqlite3.Connection]]:
    opened: list[sqlite3.Connection] = []

    def build(**options: bool) -> sqlite3.Connection:
        connection = build_recommend_database(**options)
        opened.append(connection)
        return connection

    yield build
    for connection in opened:
        connection.close()


def assert_strict_json(result: dict) -> None:
    json.dumps(result, allow_nan=False)


def assert_error(result: dict, error_type: str) -> None:
    assert list(result) == ["error"]
    assert result["error"]["type"] == error_type
    assert isinstance(result["error"]["message"], str)
    assert_strict_json(result)


def run(connection: sqlite3.Connection, name: str, **arguments: Any) -> dict:
    return call_tool(connection, name, arguments)


def schema_of(name: str) -> dict:
    return next(entry["function"] for entry in TOOL_SCHEMAS if entry["function"]["name"] == name)


def paths_in(rows: list[dict]) -> list[str]:
    return [row["path"] for row in rows]


# region valid calls


def test_call_tool_recommend_all_base(tool_database: sqlite3.Connection) -> None:
    result = call_tool(tool_database, "recommend", VALID_ARGUMENTS["recommend"])
    assert list(result) == ["recommendations"]
    rows = result["recommendations"]
    assert paths_in(rows) == ["3-0-0", "0-0-4"]
    for row in rows:
        assert set(row) == RECOMMENDATION_KEYS
        assert isinstance(row["reasons"], list)
        assert row["reasons"][0] == "affordable"
    assert rows[0]["reasons"] == ["affordable", "pops_lead", "high_pierce"]
    assert rows[0]["total_cost"] == 27000
    assert rows[0]["score"] == pytest.approx(600 / 27000, rel=1e-6)
    assert_strict_json(result)


def test_call_tool_get_round_threats_valid(tool_database: sqlite3.Connection) -> None:
    result = run(tool_database, "get_round_threats", round=63)
    assert result["round"] == 63
    assert result["property_share"]["lead"] == pytest.approx(0.1197, abs=1e-4)
    assert result["camo_share"] == 0.0
    assert {"total_rbe", "moab_share", "regrow_share", "unknown_groups", "mean_layers"} <= set(
        result
    )
    assert_strict_json(result)


def test_call_tool_get_round_threats_moab_round(tool_database: sqlite3.Connection) -> None:
    assert run(tool_database, "get_round_threats", round=40)["moab_share"] == 1.0


def test_call_tool_search_upgrades_valid(tool_database: sqlite3.Connection) -> None:
    result = call_tool(tool_database, "search_upgrades", VALID_ARGUMENTS["search_upgrades"])
    assert list(result) == ["upgrades"]
    [row] = result["upgrades"]
    assert row["path"] == "0-0-4"
    assert row["tower_name"] == "Super Monkey"
    assert row["can_hit_camo"] is True
    assert set(row) == SEARCH_KEYS
    assert_strict_json(result)


def test_call_tool_search_upgrades_flags_are_booleans(
    tool_database: sqlite3.Connection,
) -> None:
    rows = run(tool_database, "search_upgrades", limit=50)["upgrades"]
    assert len(rows) == 4
    for row in rows:
        for key in FLAG_KEYS:
            assert row[key] is None or isinstance(row[key], bool)
    assert {row["path"]: row["can_pop_lead"] for row in rows} == {
        "0-0-0": False,
        "1-0-0": False,
        "3-0-0": True,
        "0-0-4": True,
    }


def test_call_tool_search_upgrades_sorted_with_limit(tool_database: sqlite3.Connection) -> None:
    result = run(tool_database, "search_upgrades", sort_by="projectile_pierce", limit=2)
    assert paths_in(result["upgrades"]) == ["0-0-4", "3-0-0"]
    ascending = run(
        tool_database, "search_upgrades", sort_by="projectile_pierce", descending=False, limit=1
    )
    assert paths_in(ascending["upgrades"]) == ["0-0-0"]


def test_call_tool_search_upgrades_no_match(tool_database: sqlite3.Connection) -> None:
    result = run(tool_database, "search_upgrades", tower_name_contains="Nonexistent")
    assert result == {"upgrades": []}


def test_call_tool_rank_upgrades_valid(tool_database: sqlite3.Connection) -> None:
    result = call_tool(tool_database, "rank_upgrades", VALID_ARGUMENTS["rank_upgrades"])
    assert list(result) == ["upgrades"]
    rows = result["upgrades"]
    assert paths_in(rows) == ["3-0-0", "0-0-4"]
    for row in rows:
        assert set(row) == set(RANK_KEYS)
    assert rows[0]["total_cost"] == 27000
    assert isinstance(rows[0]["total_cost"], int)
    assert rows[0]["dps"] == pytest.approx(100.0, rel=1e-6)
    assert rows[0]["pierce_weighted_dps"] == pytest.approx(600.0, rel=1e-6)
    assert_strict_json(result)


def test_call_tool_rank_upgrades_camo_is_boolean(tool_database: sqlite3.Connection) -> None:
    rows = run(tool_database, "rank_upgrades", limit=50)["upgrades"]
    assert {row["path"]: row["can_hit_camo"] for row in rows}["0-0-4"] is True
    assert all(isinstance(row["can_hit_camo"], bool) for row in rows)


def test_call_tool_rank_upgrades_defaults(tool_database: sqlite3.Connection) -> None:
    rows = run(tool_database, "rank_upgrades")["upgrades"]
    assert len(rows) == 4
    ordered = [row["damage_per_dollar"] for row in rows]
    assert ordered == sorted(ordered, reverse=True)


def test_call_tool_rank_upgrades_costs_not_loaded(
    database_factory: Callable[..., sqlite3.Connection],
) -> None:
    connection = database_factory(with_costs=False)
    result = run(connection, "rank_upgrades", limit=50)
    assert len(result["upgrades"]) == 4
    assert all(row["total_cost"] is None for row in result["upgrades"])
    assert_strict_json(result)


def test_call_tool_total_cost_valid(tool_database: sqlite3.Connection) -> None:
    result = call_tool(tool_database, "total_cost", VALID_ARGUMENTS["total_cost"])
    assert result == {
        "tower_name": "Super Monkey",
        "path": "1-0-0",
        "difficulty": "medium",
        "total_cost": 4500,
    }


def test_call_tool_total_cost_easy(tool_database: sqlite3.Connection) -> None:
    result = run(
        tool_database, "total_cost", tower_name="Super Monkey", path="0-0-0", difficulty="easy"
    )
    assert result["difficulty"] == "easy"
    assert result["total_cost"] == 2125
    assert isinstance(result["total_cost"], int)


def test_call_tool_total_cost_costs_not_loaded(
    database_factory: Callable[..., sqlite3.Connection],
) -> None:
    connection = database_factory(with_costs=False)
    result = run(connection, "total_cost", tower_name="Super Monkey", path="0-0-0")
    assert result["total_cost"] is None
    assert_strict_json(result)


def test_call_tool_recommend_money_too_low(tool_database: sqlite3.Connection) -> None:
    assert run(tool_database, "recommend", round=1, money=2499) == {"recommendations": []}


def test_call_tool_recommend_limit(tool_database: sqlite3.Connection) -> None:
    arguments = {"round": 1, "money": 100000, "horizon": 1}
    default = run(tool_database, "recommend", **arguments)["recommendations"]
    assert paths_in(default) == ["3-0-0", "1-0-0", "0-0-0", "0-0-4"]
    limited = run(tool_database, "recommend", limit=1, **arguments)
    assert paths_in(limited["recommendations"]) == ["3-0-0"]


def test_call_tool_recommend_camo_round(tool_database: sqlite3.Connection) -> None:
    rows = run(tool_database, "recommend", round=101, money=100000)["recommendations"]
    assert paths_in(rows) == ["0-0-4"]
    assert rows[0]["reasons"][:2] == ["affordable", "hits_camo"]


def test_call_tool_recommend_horizon_is_passed_through(
    tool_database: sqlite3.Connection,
) -> None:
    arguments = {"round": 100, "money": 100000}
    short = run(tool_database, "recommend", horizon=1, **arguments)["recommendations"]
    long = run(tool_database, "recommend", horizon=5, **arguments)["recommendations"]
    assert {row["first_leak_round"] for row in short} == {None}
    leaks = {row["path"]: row["first_leak_round"] for row in long}
    assert leaks == {"0-0-4": None, "0-0-0": 101, "1-0-0": 101, "3-0-0": 101}
    assert paths_in(long)[0] == "0-0-4"
    assert long[1]["reasons"][-1] == "fails_camo_at_101"
    assert_strict_json({"recommendations": long})


def test_call_tool_recommend_default_horizon_is_five(tool_database: sqlite3.Connection) -> None:
    arguments = {"round": 100, "money": 100000}
    default = run(tool_database, "recommend", **arguments)
    assert default == run(tool_database, "recommend", horizon=5, **arguments)


def test_call_tool_recommend_easy_cost(tool_database: sqlite3.Connection) -> None:
    rows = run(tool_database, "recommend", round=1, money=100000, difficulty="easy")
    costs = {row["path"]: row["total_cost"] for row in rows["recommendations"]}
    assert costs["0-0-0"] == 2125


# endregion
# region invalid input


def test_call_tool_unknown_tool(tool_database: sqlite3.Connection) -> None:
    result = call_tool(tool_database, "delete_everything", {})
    assert_error(result, "UnknownTool")


def test_call_tool_unknown_argument(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "recommend", round=1, money=10, colour="red"), "TypeError")


def test_call_tool_missing_required_argument(tool_database: sqlite3.Connection) -> None:
    assert_error(call_tool(tool_database, "recommend", {}), "TypeError")


def test_call_tool_get_round_threats_wrong_type(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "get_round_threats", round="63"), "TypeError")


def test_call_tool_get_round_threats_out_of_range(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "get_round_threats", round=150), "ValueError")


def test_call_tool_get_round_threats_round_zero(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "get_round_threats", round=0), "ValueError")


def test_call_tool_get_round_threats_no_rounds(
    database_factory: Callable[..., sqlite3.Connection],
) -> None:
    connection = database_factory(with_rounds=False)
    assert_error(run(connection, "get_round_threats", round=1), "NoRoundDataError")


def test_call_tool_get_round_threats_missing_round(tool_database: sqlite3.Connection) -> None:
    assert_error(call_tool(tool_database, "get_round_threats", {}), "TypeError")


def test_call_tool_search_upgrades_bad_sort(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "search_upgrades", sort_by="colour"), "QueryError")


def test_call_tool_search_upgrades_limit_zero(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "search_upgrades", limit=0), "QueryError")


def test_call_tool_search_upgrades_unknown_argument(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "search_upgrades", colour="red"), "TypeError")


def test_call_tool_search_upgrades_limit_wrong_type(tool_database: sqlite3.Connection) -> None:
    result = run(tool_database, "search_upgrades", limit="1")
    assert "error" in result
    assert_strict_json(result)


def test_call_tool_rank_upgrades_bad_metric(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "rank_upgrades", metric="luck"), "QueryError")


def test_call_tool_rank_upgrades_bad_difficulty(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "rank_upgrades", difficulty="nightmare"), "QueryError")


def test_call_tool_rank_upgrades_unknown_filter(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "rank_upgrades", filters={"colour": "red"}), "TypeError")


def test_call_tool_rank_upgrades_limit_zero(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "rank_upgrades", limit=0), "QueryError")


def test_call_tool_recommend_negative_money(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "recommend", round=1, money=-1), "QueryError")


def test_call_tool_recommend_bad_difficulty(tool_database: sqlite3.Connection) -> None:
    result = run(tool_database, "recommend", round=1, money=10, difficulty="nightmare")
    assert_error(result, "QueryError")


def test_call_tool_recommend_round_not_loaded(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "recommend", round=150, money=10), "QueryError")


@pytest.mark.parametrize("horizon", [0, -1])
def test_call_tool_recommend_horizon_too_small(
    tool_database: sqlite3.Connection, horizon: int
) -> None:
    result = run(tool_database, "recommend", round=1, money=10, horizon=horizon)
    assert_error(result, "QueryError")
    assert f"horizon must be at least 1, got {horizon}" in result["error"]["message"]


def test_call_tool_recommend_horizon_wrong_type(tool_database: sqlite3.Connection) -> None:
    result = run(tool_database, "recommend", round=1, money=10, horizon="5")
    assert_error(result, "QueryError")


def test_call_tool_recommend_money_wrong_type(tool_database: sqlite3.Connection) -> None:
    result = run(tool_database, "recommend", round=1, money="5000")
    assert result["error"]["type"] in {"TypeError", "QueryError"}
    assert_strict_json(result)


def test_call_tool_recommend_missing_money(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "recommend", round=1), "TypeError")


def test_call_tool_recommend_no_rounds(database_factory: Callable[..., sqlite3.Connection]) -> None:
    connection = database_factory(with_rounds=False)
    assert_error(run(connection, "recommend", round=1, money=100000), "NoRoundDataError")


def test_call_tool_total_cost_bad_path(tool_database: sqlite3.Connection) -> None:
    result = run(tool_database, "total_cost", tower_name="Super Monkey", path="9-0-0")
    assert_error(result, "QueryError")


def test_call_tool_total_cost_unknown_tower(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "total_cost", tower_name="Nope", path="0-0-0"), "QueryError")


def test_call_tool_total_cost_bad_difficulty(tool_database: sqlite3.Connection) -> None:
    result = run(
        tool_database, "total_cost", tower_name="Super Monkey", path="0-0-0", difficulty="x"
    )
    assert_error(result, "QueryError")


def test_call_tool_total_cost_missing_path(tool_database: sqlite3.Connection) -> None:
    assert_error(run(tool_database, "total_cost", tower_name="Super Monkey"), "TypeError")


# endregion


def test_tool_schemas_openai_shape() -> None:
    assert len(TOOL_SCHEMAS) == 5
    for entry in TOOL_SCHEMAS:
        assert set(entry) == {"type", "function"}
        assert entry["type"] == "function"
        assert {"name", "description", "parameters"} <= set(entry["function"])
        assert entry["function"]["parameters"]["type"] == "object"


def test_tool_schemas_names() -> None:
    assert [entry["function"]["name"] for entry in TOOL_SCHEMAS] == TOOL_NAMES


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_tool_schemas_required(name: str) -> None:
    assert schema_of(name)["parameters"].get("required", []) == REQUIRED[name]


def test_tool_schemas_metric_enum() -> None:
    metric = schema_of("rank_upgrades")["parameters"]["properties"]["metric"]
    assert metric["enum"] == list(METRICS)


@pytest.mark.parametrize("name", ["rank_upgrades", "recommend", "total_cost"])
def test_tool_schemas_difficulty_enum(name: str) -> None:
    difficulty = schema_of(name)["parameters"]["properties"]["difficulty"]
    assert difficulty["enum"] == list(tuple(DIFFICULTY_MULTIPLIERS))


def test_tool_schemas_recommend_horizon_is_optional_integer() -> None:
    parameters = schema_of("recommend")["parameters"]
    horizon = parameters["properties"]["horizon"]
    assert horizon["type"] == "integer"
    assert horizon["minimum"] == 1
    assert "horizon" not in parameters.get("required", [])


def test_tool_schemas_json_serializable() -> None:
    json.dumps(TOOL_SCHEMAS, allow_nan=False)
    for entry in TOOL_SCHEMAS:
        assert isinstance(entry["function"]["description"], str)
        assert entry["function"]["description"].strip()


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_tool_schemas_names_are_dispatchable(name: str, tool_database: sqlite3.Connection) -> None:
    result = call_tool(tool_database, name, VALID_ARGUMENTS[name])
    assert "error" not in result


def test_tool_schemas_filter_properties() -> None:
    search = schema_of("search_upgrades")["parameters"]["properties"]
    rank = schema_of("rank_upgrades")["parameters"]["properties"]["filters"]["properties"]
    assert FILTER_NAMES <= set(search)
    assert set(rank) == FILTER_NAMES


json_scalars = st.none() | st.booleans() | st.integers(-5, 200) | st.text(max_size=8)
arguments_strategy = st.dictionaries(
    st.sampled_from(
        ["round", "money", "limit", "path", "tower_name", "metric", "difficulty", "filters", "x"]
    ),
    json_scalars | st.dictionaries(st.text(max_size=5), json_scalars, max_size=2),
    max_size=4,
)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=60)
@given(name=st.sampled_from([*TOOL_NAMES, "bogus"]), arguments=arguments_strategy)
def test_call_tool_never_raises(
    shared_database: sqlite3.Connection, name: str, arguments: dict
) -> None:
    result = call_tool(shared_database, name, arguments)
    assert isinstance(result, dict)
    assert_strict_json(result)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=40)
@given(money=st.integers(0, 200000), round_number=st.sampled_from([1, 40, 63, 101]))
def test_call_tool_recommend_never_exceeds_money(
    shared_database: sqlite3.Connection, money: int, round_number: int
) -> None:
    result = call_tool(shared_database, "recommend", {"round": round_number, "money": money})
    assert_strict_json(result)
    assert all(row["total_cost"] <= money for row in result["recommendations"])


# region recommend: one_per_tower and owned

OWNED_ARGUMENTS = {"round": 63, "money": 100000, "horizon": 1}


def test_tool_schemas_recommend_one_per_tower_is_optional_boolean() -> None:
    parameters = schema_of("recommend")["parameters"]
    assert parameters["properties"]["one_per_tower"]["type"] == "boolean"
    assert "one_per_tower" not in parameters.get("required", [])


def test_tool_schemas_recommend_owned_is_optional_array_of_strings() -> None:
    parameters = schema_of("recommend")["parameters"]
    owned = parameters["properties"]["owned"]
    assert owned["type"] == "array"
    assert owned["items"]["type"] == "string"
    assert "owned" not in parameters.get("required", [])


def test_call_tool_recommend_one_per_tower_is_passed_through(
    tool_database: sqlite3.Connection,
) -> None:
    arguments = {"round": 1, "money": 100000, "horizon": 1}
    everything = run(tool_database, "recommend", limit=10, **arguments)["recommendations"]
    single = run(tool_database, "recommend", one_per_tower=True, **arguments)["recommendations"]
    assert len(everything) == 4
    assert single == everything[:1]
    assert run(tool_database, "recommend", one_per_tower=False, limit=10, **arguments) == {
        "recommendations": everything
    }


def test_call_tool_recommend_owned_is_passed_through(tool_database: sqlite3.Connection) -> None:
    rows = run(
        tool_database, "recommend", owned=["Super Monkey 0-0-0"], limit=10, **OWNED_ARGUMENTS
    )["recommendations"]
    upgrades = {row["path"]: row for row in rows if row["upgrade_from"] is not None}
    assert set(upgrades) == {"3-0-0", "0-0-4"}
    assert upgrades["3-0-0"]["upgrade_from"] == "0-0-0"
    assert upgrades["3-0-0"]["total_cost"] == 24500
    assert "upgrades_owned" in upgrades["3-0-0"]["reasons"]
    assert_strict_json({"recommendations": rows})


def test_call_tool_recommend_owned_covers_needs(tool_database: sqlite3.Connection) -> None:
    arguments = {"round": 101, "money": 100000, "horizon": 1, "limit": 10}
    alone = run(tool_database, "recommend", **arguments)["recommendations"]
    covered = run(tool_database, "recommend", owned=["Super Monkey 0-0-4"], **arguments)
    assert paths_in(alone) == ["0-0-4"]
    assert len(covered["recommendations"]) == 4


def test_call_tool_recommend_owned_empty_list_is_no_owned(
    tool_database: sqlite3.Connection,
) -> None:
    assert run(tool_database, "recommend", owned=[], **OWNED_ARGUMENTS) == run(
        tool_database, "recommend", **OWNED_ARGUMENTS
    )


def test_call_tool_recommend_owned_unknown_tower_is_ignored(
    tool_database: sqlite3.Connection,
) -> None:
    result = run(tool_database, "recommend", owned=["Banana Farm 2-0-0"], **OWNED_ARGUMENTS)
    assert result == run(tool_database, "recommend", **OWNED_ARGUMENTS)


@pytest.mark.parametrize("entry", ["Ninja", "Super Monkey", "Super Monkey 1-2", "0-0-0", ""])
def test_call_tool_recommend_owned_bad_string(
    tool_database: sqlite3.Connection, entry: str
) -> None:
    result = run(tool_database, "recommend", owned=[entry], **OWNED_ARGUMENTS)
    assert_error(result, "QueryError")
    assert result["error"]["message"] == f"owned must be '<tower name> X-Y-Z', got {entry!r}"


def test_call_tool_recommend_owned_path_out_of_range(tool_database: sqlite3.Connection) -> None:
    result = run(tool_database, "recommend", owned=["Super Monkey 6-0-0"], **OWNED_ARGUMENTS)
    assert_error(result, "QueryError")


@pytest.mark.parametrize("value", ["yes", 1, "true"])
def test_call_tool_recommend_one_per_tower_wrong_type(
    tool_database: sqlite3.Connection, value: object
) -> None:
    result = run(tool_database, "recommend", one_per_tower=value, **OWNED_ARGUMENTS)
    assert_error(result, "QueryError")
    assert result["error"]["message"] == f"one_per_tower must be true or false, got {value!r}"


# endregion
