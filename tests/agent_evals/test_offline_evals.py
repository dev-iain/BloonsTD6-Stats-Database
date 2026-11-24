from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from btd6.agent.loop import run_agent
from btd6.agent.picks import AgentResult
from tests.agent_evals.checks import (
    picks_affordable,
    picks_grounded,
    picks_known_towers,
    run_all_checks,
)
from tests.agent_evals.reactive_stub import ReactiveStub
from tests.agent_evals.scenarios import build_offline_connection, load_scenarios
from tests.agent_stub import ScriptedClient, final_message, tool_call_message
from tests.recommend_fixture import build_recommend_database

SCENARIOS = load_scenarios()


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[scenario["id"] for scenario in SCENARIOS])
def test_scripted_run_passes_all_checks(scenario: dict[str, Any]) -> None:
    connection = build_offline_connection(scenario)
    stub = ReactiveStub(scenario["round"], scenario["money"], scenario["difficulty"])

    result = run_agent(
        connection, stub, scenario["round"], scenario["money"], scenario["difficulty"]
    )

    assert run_all_checks(scenario, result, connection) == []
    connection.close()


def scripted_result(final_text: str, money: int = 100000) -> tuple[sqlite3.Connection, AgentResult]:
    connection = build_recommend_database()
    script = [
        tool_call_message(("recommend", {"round": 63, "money": money})),
        final_message(final_text),
    ]
    return connection, run_agent(connection, ScriptedClient(script), 63, money)


def test_invented_pick_is_caught() -> None:
    connection, result = scripted_result("Picks:\n- Ninja Monkey 5-0-0 $1")

    grounded = picks_grounded("invented", result, connection, 100000)
    known = picks_known_towers("invented", result, connection, 100000)

    assert grounded and "invented" in grounded[0] and "Ninja Monkey" in grounded[0]
    assert known and "invented" in known[0]
    assert picks_affordable("invented", result, connection, 100000) == []


def test_real_tower_but_unreturned_path_is_ungrounded() -> None:
    connection, result = scripted_result("Picks:\n- Super Monkey 0-0-0 $2,500")

    assert picks_grounded("unreturned", result, connection, 100000) != []
    assert picks_known_towers("unreturned", result, connection, 100000) == []


def test_over_budget_pick_is_caught() -> None:
    connection, result = scripted_result("Picks:\n- Super Monkey 3-0-0 $27,000")

    failures = picks_affordable("overspend", result, connection, 10000)

    assert len(failures) == 1 and "overspend" in failures[0]
    assert picks_affordable("overspend", result, connection, 27000) == []
