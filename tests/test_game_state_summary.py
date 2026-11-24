from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from btd6.game_state import StoredGameState, parse_game_state, state_summary

VALID_PATH = Path(__file__).parent / "fixtures" / "game_state" / "valid.json"
RECEIVED_AT = datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)


def stored_state(**overrides: object) -> StoredGameState:
    payload = json.loads(VALID_PATH.read_text(encoding="utf-8"))
    payload.update(overrides)
    return StoredGameState(parse_game_state(payload), RECEIVED_AT)


def after(seconds: float) -> datetime:
    return RECEIVED_AT + timedelta(seconds=seconds)


def test_state_summary_all_base():
    summary = state_summary(stored_state(), after(10), 30)
    assert summary == {
        "round": 40,
        "money": 5123,
        "lives": 150,
        "difficulty": "medium",
        "mode": "Standard",
        "map": "Monkey Meadow",
        "towers": [
            {"base_id": "DartMonkey", "tower_name": "Dart Monkey", "path": "0-2-3", "known": True},
            {"base_id": "BananaFarm", "tower_name": None, "path": "2-0-0", "known": False},
        ],
        "received_at": "2026-11-24T12:00:00+00:00",
        "age_seconds": 10.0,
        "stale": False,
    }


def test_state_summary_is_json_serialisable():
    summary = state_summary(stored_state(), after(10), 30)
    assert json.loads(json.dumps(summary)) == summary


def test_state_summary_at_limit():
    summary = state_summary(stored_state(), after(30), 30)
    assert (summary["age_seconds"], summary["stale"]) == (30.0, False)


def test_state_summary_over_limit():
    summary = state_summary(stored_state(), after(31), 30)
    assert (summary["age_seconds"], summary["stale"]) == (31.0, True)


def test_state_summary_no_limit():
    summary = state_summary(stored_state(), after(3600), None)
    assert (summary["age_seconds"], summary["stale"]) == (3600.0, False)


def test_state_summary_default_limit_is_thirty_seconds():
    assert state_summary(stored_state(), after(31))["stale"] is True
    assert state_summary(stored_state(), after(30))["stale"] is False


def test_state_summary_impoppable():
    summary = state_summary(stored_state(difficulty="Hard", mode="Impoppable"), after(10), 30)
    assert (summary["difficulty"], summary["mode"]) == ("impoppable", "Impoppable")


def test_state_summary_no_towers():
    assert state_summary(stored_state(towers=[]), after(10), 30)["towers"] == []
