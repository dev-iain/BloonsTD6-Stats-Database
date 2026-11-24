from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from btd6.agent.loop import run_agent
from btd6.game_state import fake_game_state, save_game_state
from tests.agent_evals.checks import run_all_checks
from tests.agent_evals.reactive_stub import compose_answer
from tests.agent_stub import final_message, tool_call_message
from tests.recommend_fixture import build_recommend_database

LIVE_STATE = fake_game_state(63, 100000, "medium", [("Super Monkey", "2-0-0")])
SCENARIO = {
    "id": "live_state",
    "round": 63,
    "money": 100000,
    "difficulty": "medium",
    "expectation": "lead_pierce",
    "database": "full",
    "live": False,
}


class LiveStub:
    """Reads the live state with get_game_state, then recommends from its round and money."""

    def __init__(self) -> None:
        self.call_count = 0

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        self.call_count += 1
        if self.call_count == 1:
            return tool_call_message(("get_game_state", {}))
        if self.call_count == 2:
            state = json.loads(messages[-1]["content"])
            arguments = {
                "round": state["round"],
                "money": state["money"],
                "difficulty": state["difficulty"],
            }
            return tool_call_message(("recommend", arguments))
        return final_message(compose_answer(messages[-1]["content"]))


def test_live_state_scenario_passes_all_checks(tmp_path: Path) -> None:
    state_path = tmp_path / "game_state.json"
    save_game_state(state_path, LIVE_STATE, datetime.now(UTC))
    connection = build_recommend_database()

    result = run_agent(
        connection,
        LiveStub(),
        LIVE_STATE.round_number,
        LIVE_STATE.money,
        LIVE_STATE.difficulty,
        state_path=state_path,
        owned_towers=LIVE_STATE.towers,
    )

    assert [call.name for call in result.tool_calls] == ["get_game_state", "recommend"]
    assert result.tool_calls[1].arguments["money"] == 100000
    assert result.picks
    assert run_all_checks(SCENARIO, result, connection) == []
    connection.close()
