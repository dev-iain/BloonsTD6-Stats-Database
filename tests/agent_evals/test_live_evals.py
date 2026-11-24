from __future__ import annotations

import os
from typing import Any

import pytest

from btd6.agent.client import API_KEY_VARIABLE, client_from_environment
from btd6.agent.loop import run_agent
from btd6.etl.fetch import PROJECT_ROOT
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
