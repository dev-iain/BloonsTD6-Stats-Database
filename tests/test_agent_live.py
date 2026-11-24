from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from btd6.agent.loop import LIVE_PROMPT, SYSTEM_PROMPT, run_agent
from btd6.agent.schemas import LIVE_TOOL_SCHEMAS, TOOL_SCHEMAS
from btd6.agent.tools import NOT_LIVE_MESSAGE, call_tool, execute_call
from btd6.game_state import PlacedTower, fake_game_state, save_game_state
from tests.agent_stub import ScriptedClient, final_message, tool_call_message
from tests.recommend_fixture import build_recommend_database

LIVE_STATE = fake_game_state(63, 100000, "medium", [("Super Monkey", "2-0-0")])
UNKNOWN_TOWER = PlacedTower("BananaFarm", None, "2-0-0", False)


@pytest.fixture
def connection():
    connection = build_recommend_database()
    yield connection
    connection.close()


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "game_state.json"


def write_state(state_path: Path, age_seconds: float = 0) -> None:
    save_game_state(state_path, LIVE_STATE, datetime.now(UTC) - timedelta(seconds=age_seconds))


def test_live_tool_schemas_add_get_game_state() -> None:
    names = [schema["function"]["name"] for schema in LIVE_TOOL_SCHEMAS]
    assert LIVE_TOOL_SCHEMAS[: len(TOOL_SCHEMAS)] == TOOL_SCHEMAS
    assert names[len(TOOL_SCHEMAS) :] == ["get_game_state"]
    assert "get_game_state" not in [schema["function"]["name"] for schema in TOOL_SCHEMAS]


def test_call_tool_get_game_state_all_base(connection, state_path: Path) -> None:
    write_state(state_path)

    result = call_tool(connection, "get_game_state", {}, state_path=state_path)

    assert (result["round"], result["money"], result["difficulty"]) == (63, 100000, "medium")
    assert result["towers"] == [
        {"base_id": "SuperMonkey", "tower_name": "Super Monkey", "path": "2-0-0", "known": True}
    ]
    assert result["stale"] is False


def test_call_tool_get_game_state_not_live(connection, state_path: Path) -> None:
    write_state(state_path)

    result = call_tool(connection, "get_game_state", {})

    assert result["error"] == {"type": "LiveStateUnavailable", "message": NOT_LIVE_MESSAGE}
    assert "--live" in NOT_LIVE_MESSAGE


def test_call_tool_get_game_state_stale(connection, state_path: Path) -> None:
    write_state(state_path, age_seconds=3600)

    result = call_tool(connection, "get_game_state", {}, state_path=state_path)

    assert result["error"]["type"] == "StaleGameStateError"
    assert result["error"]["message"].startswith("Game state is stale: received 3600 s ago")


def test_call_tool_get_game_state_missing(connection, state_path: Path) -> None:
    result = call_tool(connection, "get_game_state", {}, state_path=state_path)

    assert result["error"]["type"] == "NoGameStateError"
    assert result["error"]["message"].startswith(f"No game state at {state_path}")


def test_call_tool_get_game_state_unexpected_argument(connection, state_path: Path) -> None:
    write_state(state_path)

    result = call_tool(connection, "get_game_state", {"round": 1}, state_path=state_path)

    assert result["error"]["type"] == "TypeError"


def test_execute_call_passes_state_path(connection, state_path: Path) -> None:
    write_state(state_path)
    call = tool_call_message(("get_game_state", {}))["tool_calls"][0]

    record = execute_call(connection, call, state_path=state_path)

    assert record.result["round"] == 63


def run_live(connection, state_path: Path, owned_towers, client: ScriptedClient | None = None):
    client = client or ScriptedClient([final_message("Picks:\n- none")])
    result = run_agent(
        connection,
        client,
        63,
        100000,
        state_path=state_path,
        owned_towers=owned_towers,
    )
    return client, result


def test_run_agent_live_all_base(connection, state_path: Path) -> None:
    write_state(state_path)
    client = ScriptedClient(
        [tool_call_message(("get_game_state", {})), final_message("Picks:\n- none")]
    )

    client, result = run_live(connection, state_path, LIVE_STATE.towers, client)

    messages, tools = client.requests[0]
    assert messages[0]["content"] == SYSTEM_PROMPT + "\n" + LIVE_PROMPT
    assert messages[1]["content"] == (
        "Round 63, money $100000, difficulty medium. You own: Super Monkey 2-0-0. "
        "Recommend what to buy."
    )
    assert tools == LIVE_TOOL_SCHEMAS
    assert result.tool_calls[0].result["round"] == 63


def test_run_agent_live_no_state_path(connection) -> None:
    client, _ = run_live(connection, None, LIVE_STATE.towers)

    messages, tools = client.requests[0]
    assert tools == TOOL_SCHEMAS
    assert messages[0]["content"] == SYSTEM_PROMPT


def test_run_agent_live_unknown_tower(connection, state_path: Path) -> None:
    client, _ = run_live(connection, state_path, (*LIVE_STATE.towers, UNKNOWN_TOWER))

    assert (
        "You own: Super Monkey 2-0-0, BananaFarm 2-0-0 (not in the database)."
        in client.requests[0][0][1]["content"]
    )


def test_run_agent_live_no_towers(connection, state_path: Path) -> None:
    client, _ = run_live(connection, state_path, ())

    assert "You own no towers." in client.requests[0][0][1]["content"]


def test_run_agent_live_owned_none(connection, state_path: Path) -> None:
    client, _ = run_live(connection, state_path, None)

    assert client.requests[0][0][1]["content"] == (
        "Round 63, money $100000, difficulty medium. Recommend what to buy."
    )
