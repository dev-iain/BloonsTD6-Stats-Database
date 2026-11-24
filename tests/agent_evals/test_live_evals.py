from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from btd6.agent.client import API_KEY_VARIABLE, client_from_environment
from btd6.agent.loop import run_agent
from btd6.etl.fetch import PROJECT_ROOT
from btd6.game_state import fake_game_state, save_game_state
from tests.agent_evals.checks import run_all_checks
from tests.agent_evals.scenarios import build_live_connection, load_scenarios

SCENARIOS = load_scenarios(live_only=True)
DATABASE_PATH = PROJECT_ROOT / "btd6.db"

pytestmark = [
    pytest.mark.live_agent,
    pytest.mark.skipif(
        not os.environ.get(API_KEY_VARIABLE), reason=f"{API_KEY_VARIABLE} is not set"
    ),
    pytest.mark.skipif(not DATABASE_PATH.exists(), reason="btd6.db is missing"),
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[scenario["id"] for scenario in SCENARIOS])
def test_live_scenario(scenario: dict[str, Any]) -> None:
    connection = build_live_connection(scenario, DATABASE_PATH)
    client = client_from_environment(os.environ)

    result = run_agent(
        connection, client, scenario["round"], scenario["money"], scenario["difficulty"]
    )

    failures = run_all_checks(scenario, result, connection)
    connection.close()
    assert not failures, "\n".join(failures)


LIVE_SCENARIO = {
    "id": "live_state_round63",
    "round": 63,
    "money": 100000,
    "difficulty": "medium",
    "expectation": "lead_pierce",
    "database": "full",
    "live": True,
}


def test_live_state_scenario(tmp_path: Path) -> None:
    state = fake_game_state(63, 100000, "medium", [("Super Monkey", "2-0-0")])
    state_path = tmp_path / "game_state.json"
    save_game_state(state_path, state, datetime.now(UTC))
    connection = build_live_connection(LIVE_SCENARIO, DATABASE_PATH)

    result = run_agent(
        connection,
        client_from_environment(os.environ),
        state.round_number,
        state.money,
        state.difficulty,
        state_path=state_path,
        owned_towers=state.towers,
    )

    failures = run_all_checks(LIVE_SCENARIO, result, connection)
    connection.close()
    assert not failures, "\n".join(failures)
