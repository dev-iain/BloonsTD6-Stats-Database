from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from btd6.api import create_app
from btd6.game_state import fake_game_state, parse_game_state, save_game_state

URL = "/api/game-state"
VALID_PATH = Path(__file__).parent / "fixtures" / "game_state" / "valid.json"
RECEIVED_AT = datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)
VALID = json.loads(VALID_PATH.read_text(encoding="utf-8"))


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "game_state.json"


@pytest.fixture
def clock() -> Clock:
    return Clock(RECEIVED_AT)


@pytest.fixture
def client(tmp_path: Path, state_path: Path, clock: Clock) -> TestClient:
    return TestClient(create_app(tmp_path / "btd6.db", state_path=state_path, clock=clock))


def save_valid(state_path: Path) -> None:
    save_game_state(state_path, parse_game_state(VALID), RECEIVED_AT)


def stored_round(state_path: Path) -> int:
    return json.loads(state_path.read_text(encoding="utf-8"))["round"]


def test_post_game_state_all_base(client: TestClient, state_path: Path) -> None:
    response = client.post(URL, json=VALID)

    assert response.status_code == 200
    body = response.json()
    assert (body["round"], body["money"]) == (40, 5123)
    assert (body["age_seconds"], body["stale"]) == (0.0, False)
    stored = json.loads(state_path.read_text(encoding="utf-8"))
    assert stored["round"] == 40
    assert stored["received_at"] == "2026-11-24T12:00:00+00:00"


def test_post_game_state_invalid_payload(client: TestClient, state_path: Path) -> None:
    response = client.post(URL, json={**VALID, "round": 0})

    assert response.status_code == 422
    assert response.json() == {"error": "round must be an integer >= 1"}
    assert not state_path.exists()


def test_post_game_state_not_object(client: TestClient, state_path: Path) -> None:
    response = client.post(URL, json=[1, 2])

    assert response.status_code == 422
    assert response.json() == {"error": "Game state must be a JSON object"}
    assert not state_path.exists()


def test_post_game_state_not_json(client: TestClient, state_path: Path) -> None:
    response = client.post(URL, content=b"not json", headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert response.json() == {"error": "Game state must be a JSON object"}
    assert not state_path.exists()


def test_post_game_state_replaces_older_state(client: TestClient, state_path: Path) -> None:
    save_game_state(state_path, fake_game_state(12, 900), RECEIVED_AT)

    response = client.post(URL, json=VALID)

    assert response.status_code == 200
    assert stored_round(state_path) == 40


def test_get_game_state_all_base(client: TestClient, state_path: Path, clock: Clock) -> None:
    save_valid(state_path)
    clock.now = RECEIVED_AT + timedelta(seconds=5)

    response = client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert body["round"] == 40
    assert (body["age_seconds"], body["stale"]) == (5.0, False)
    assert body["towers"] == [
        {"base_id": "DartMonkey", "tower_name": "Dart Monkey", "path": "0-2-3", "known": True},
        {"base_id": "BananaFarm", "tower_name": None, "path": "2-0-0", "known": False},
    ]


def test_get_game_state_stale(client: TestClient, state_path: Path, clock: Clock) -> None:
    save_valid(state_path)
    clock.now = RECEIVED_AT + timedelta(seconds=60)

    response = client.get(URL)

    assert response.status_code == 200
    assert (response.json()["age_seconds"], response.json()["stale"]) == (60.0, True)


def test_get_game_state_missing(client: TestClient) -> None:
    response = client.get(URL)

    assert response.status_code == 404
    assert response.json()["error"].startswith("No game state at")


def test_get_game_state_corrupt(client: TestClient, state_path: Path) -> None:
    state_path.write_text("{", encoding="utf-8")

    response = client.get(URL)

    assert response.status_code == 422
    assert "is not valid JSON" in response.json()["error"]


def test_post_then_get_round_trip(client: TestClient) -> None:
    posted = client.post(URL, json=VALID).json()

    assert client.get(URL).json() == posted


def test_create_app_defaults_state_path_to_project_root(tmp_path: Path) -> None:
    from btd6.api.app import DEFAULT_STATE_PATH

    assert DEFAULT_STATE_PATH.name == "game_state.json"
    assert DEFAULT_STATE_PATH.parent == Path(__file__).resolve().parents[1]
