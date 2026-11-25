from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from btd6.agent.client import AgentError, MissingApiKeyError
from btd6.api import create_app
from btd6.game_state import fake_game_state, save_game_state
from tests.agent_stub import ScriptedClient, final_message, tool_call_message
from tests.income_fixture import save_connection
from tests.recommend_fixture import build_recommend_database

URL = "/api/agent"
RECEIVED_AT = datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)
ANSWER = "Pierce for lead.\nPicks:\n- Super Monkey 3-0-0 $27,000: pops lead"
PARAMS = {"round": 63, "money": 5000, "difficulty": "hard"}


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def database_path(tmp_path: Path) -> str:
    source = build_recommend_database()
    path = save_connection(source, tmp_path / "btd6.db")
    source.close()
    return path


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "game_state.json"


@pytest.fixture
def clock() -> Clock:
    return Clock(RECEIVED_AT)


@pytest.fixture
def scripted() -> ScriptedClient:
    return ScriptedClient(
        [tool_call_message(("get_round_threats", {"round": 63})), final_message(ANSWER)]
    )


def make_client(
    database_path: str,
    scripted_client: ScriptedClient,
    state_path: Path,
    clock: Clock,
) -> TestClient:
    app = create_app(
        database_path,
        state_path=state_path,
        clock=clock,
        agent_client_factory=lambda: scripted_client,
    )
    return TestClient(app)


@pytest.fixture
def client(
    database_path: str, scripted: ScriptedClient, state_path: Path, clock: Clock
) -> TestClient:
    return make_client(database_path, scripted, state_path, clock)


def first_user_message(scripted_client: ScriptedClient) -> str:
    return scripted_client.requests[0][0][1]["content"]


def test_agent_all_base(client: TestClient, scripted: ScriptedClient) -> None:
    response = client.get(URL, params=PARAMS)

    assert response.status_code == 200
    assert response.json() == {
        "answer": ANSWER,
        "picks": [
            {
                "tower_name": "Super Monkey",
                "path": "3-0-0",
                "total_cost": 27000,
                "reason": "pops lead",
            }
        ],
        "tool_calls": [{"name": "get_round_threats", "arguments": {"round": 63}}],
    }
    assert "Round 63, money $5000, difficulty hard" in first_user_message(scripted)
    assert scripted.call_count == 2


def test_agent_default_difficulty_is_medium(client: TestClient, scripted: ScriptedClient) -> None:
    response = client.get(URL, params={"round": 63, "money": 5000})

    assert response.status_code == 200
    assert "difficulty medium" in first_user_message(scripted)


def test_agent_max_iterations_param(database_path: str, state_path: Path, clock: Clock) -> None:
    looping = ScriptedClient([tool_call_message(("get_round_threats", {"round": 63}))], True)
    client = make_client(database_path, looping, state_path, clock)

    response = client.get(URL, params={**PARAMS, "max_iterations": 3})

    assert response.status_code == 502
    assert looping.call_count == 3
    assert "No final answer after 3 iterations" in response.json()["error"]


def test_agent_missing_key_is_503(database_path: str, state_path: Path, clock: Clock) -> None:
    def factory() -> ScriptedClient:
        raise MissingApiKeyError("GEMINI_API_KEY is not set.")

    app = create_app(
        database_path, state_path=state_path, clock=clock, agent_client_factory=factory
    )

    response = TestClient(app).get(URL, params=PARAMS)

    assert response.status_code == 503
    assert response.json() == {"error": "GEMINI_API_KEY is not set."}


def test_agent_default_factory_reports_missing_key(
    database_path: str, state_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("btd6.api.app.API_KEY_FILES", (tmp_path / "no.env",))

    response = TestClient(create_app(database_path, state_path=state_path)).get(URL, params=PARAMS)

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["error"]


def test_agent_default_factory_reads_key_file_per_request(
    database_path: str, state_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "gemini_api_key.txt"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("btd6.api.app.API_KEY_FILES", (key_file,))
    built_keys: list[str] = []

    def build_client(api_key: str, model: str, base_url: str) -> ScriptedClient:
        built_keys.append(api_key)
        return ScriptedClient([final_message(ANSWER)])

    monkeypatch.setattr("btd6.agent.client.OpenAICompatibleClient", build_client)
    client = TestClient(create_app(database_path, state_path=state_path))

    assert client.get(URL, params=PARAMS).status_code == 503
    key_file.write_text("pasted-key\n", encoding="utf-8")
    assert client.get(URL, params=PARAMS).status_code == 200
    assert built_keys == ["pasted-key"]


def test_agent_error_is_502(database_path: str, state_path: Path, clock: Clock) -> None:
    looping = ScriptedClient([tool_call_message(("get_round_threats", {"round": 63}))], True)
    client = make_client(database_path, looping, state_path, clock)

    response = client.get(URL, params={**PARAMS, "max_iterations": 1})

    assert response.status_code == 502
    assert "No final answer after 1 iterations" in response.json()["error"]


def test_agent_provider_error_is_502(database_path: str, state_path: Path, clock: Clock) -> None:
    class FailingClient:
        def complete(self, messages: list[dict], tools: list[dict]) -> dict:
            raise AgentError("HTTP 429 from provider")

    app = create_app(
        database_path,
        state_path=state_path,
        clock=clock,
        agent_client_factory=lambda: FailingClient(),
    )

    response = TestClient(app).get(URL, params=PARAMS)

    assert response.status_code == 502
    assert response.json() == {"error": "HTTP 429 from provider"}


@pytest.mark.parametrize(
    "params",
    [
        {"round": 63, "money": "lots"},
        {"round": 63, "money": -1},
        {"round": 63},
        {"money": 5000},
        {"round": "x", "money": 5000},
        {"round": 63, "money": 5000, "max_iterations": "many"},
    ],
    ids=["money_text", "money_negative", "no_money", "no_round", "round_text", "iterations_text"],
)
def test_agent_invalid_params_are_422(
    client: TestClient, scripted: ScriptedClient, params: dict[str, object]
) -> None:
    response = client.get(URL, params=params)

    assert response.status_code == 422
    assert "error" in response.json()
    assert scripted.call_count == 0


def test_agent_validates_before_building_client(
    database_path: str, state_path: Path, clock: Clock
) -> None:
    def factory() -> ScriptedClient:
        raise MissingApiKeyError("no key")

    app = create_app(
        database_path, state_path=state_path, clock=clock, agent_client_factory=factory
    )

    response = TestClient(app).get(URL, params={"round": 63, "money": "lots"})

    assert response.status_code == 422


def test_agent_live_passes_owned_towers(
    client: TestClient, scripted: ScriptedClient, state_path: Path
) -> None:
    state = fake_game_state(63, 5000, "hard", [("Super Monkey", "1-0-0")])
    save_game_state(state_path, state, RECEIVED_AT)

    response = client.get(URL, params={**PARAMS, "live": "true"})

    assert response.status_code == 200
    message = first_user_message(scripted)
    assert "Round 63, money $5000, difficulty hard" in message
    assert "Super Monkey 1-0-0" in message
    tool_names = {schema["function"]["name"] for schema in scripted.requests[0][1]}
    assert "get_game_state" in tool_names


def test_agent_not_live_ignores_stored_state(
    client: TestClient, scripted: ScriptedClient, state_path: Path
) -> None:
    state = fake_game_state(63, 5000, "hard", [("Super Monkey", "1-0-0")])
    save_game_state(state_path, state, RECEIVED_AT)

    response = client.get(URL, params={**PARAMS, "live": "false"})

    assert response.status_code == 200
    assert "Super Monkey 1-0-0" not in first_user_message(scripted)
    tool_names = {schema["function"]["name"] for schema in scripted.requests[0][1]}
    assert "get_game_state" not in tool_names


def test_agent_live_without_state_is_404(client: TestClient, scripted: ScriptedClient) -> None:
    response = client.get(URL, params={**PARAMS, "live": "true"})

    assert response.status_code == 404
    assert response.json()["error"].startswith("No game state at")
    assert scripted.call_count == 0


def test_agent_live_stale_state_is_422(
    client: TestClient, scripted: ScriptedClient, state_path: Path, clock: Clock
) -> None:
    save_game_state(state_path, fake_game_state(63, 5000), RECEIVED_AT)
    clock.now = RECEIVED_AT + timedelta(seconds=60)

    response = client.get(URL, params={**PARAMS, "live": "true"})

    assert response.status_code == 422
    assert "stale" in response.json()["error"]
    assert scripted.call_count == 0


def test_agent_missing_database_is_503(
    tmp_path: Path, scripted: ScriptedClient, state_path: Path, clock: Clock
) -> None:
    client = make_client(str(tmp_path / "missing.db"), scripted, state_path, clock)

    response = client.get(URL, params=PARAMS)

    assert response.status_code == 503
    assert "Database not found" in response.json()["error"]
    assert scripted.call_count == 0
