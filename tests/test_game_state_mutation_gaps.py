from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from btd6.game_state import (
    TOWER_IDS,
    GameStateError,
    fake_game_state,
    fake_tower,
    game_id_from_name,
    load_game_state,
    parse_game_state,
    parse_tower_spec,
    save_game_state,
)

RECEIVED_AT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def valid_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": 1,
        "round": 5,
        "cash": 650,
        "lives": 100,
        "difficulty": "Medium",
        "mode": "Standard",
        "map": "Cubism",
        "towers": [{"base_id": "DartMonkey", "tiers": [0, 2, 3]}],
    }
    payload.update(overrides)
    return payload


def write_payload(path: Path, received_at: str, **overrides: Any) -> Path:
    payload = {**valid_payload(**overrides), "received_at": received_at}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def raises_exactly(message: str):
    return pytest.raises(GameStateError, match=f"^{re.escape(message)}$")


def test_missing_key_message() -> None:
    payload = valid_payload()
    del payload["round"]
    with raises_exactly("Missing key: round"):
        parse_game_state(payload)


def test_integer_below_minimum_message() -> None:
    with raises_exactly("round must be an integer >= 1"):
        parse_game_state(valid_payload(round=0))


def test_negative_cash_message() -> None:
    with raises_exactly("cash must be a number >= 0"):
        parse_game_state(valid_payload(cash=-1))


def test_non_string_text_message() -> None:
    with raises_exactly("difficulty must be a string"):
        parse_game_state(valid_payload(difficulty=5))


def test_tower_not_object_message() -> None:
    with raises_exactly("Each tower must be an object"):
        parse_game_state(valid_payload(towers=["DartMonkey"]))


def test_bad_tiers_message() -> None:
    bad = {"base_id": "DartMonkey", "tiers": [0, 6, 0]}
    with raises_exactly("tiers must be three integers from 0 to 5"):
        parse_game_state(valid_payload(towers=[bad]))


def test_towers_not_list_message() -> None:
    with raises_exactly("towers must be a list"):
        parse_game_state(valid_payload(towers={}))


def test_unsupported_version_message() -> None:
    with raises_exactly("Unsupported version: 2"):
        parse_game_state(valid_payload(version=2))


def test_unknown_difficulty_message_from_parse() -> None:
    with raises_exactly("Unknown difficulty: 'Bogus'"):
        parse_game_state(valid_payload(difficulty="Bogus"))


def test_unknown_difficulty_message_from_fake() -> None:
    with raises_exactly("Unknown difficulty: 'bogus'"):
        fake_game_state(5, 100, "bogus")


def test_invalid_received_at_message(tmp_path: Path) -> None:
    path = write_payload(tmp_path / "state.json", "not a date")
    with raises_exactly("received_at is not an ISO 8601 timestamp"):
        load_game_state(path)


def test_invalid_json_file_message(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{nope", encoding="utf-8")
    with raises_exactly(f"Game state file {path} is not valid JSON"):
        load_game_state(path)


def test_non_object_json_file_message(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("[]", encoding="utf-8")
    with raises_exactly(f"Game state file {path} must hold a JSON object"):
        load_game_state(path)


def test_stale_message_is_exact(tmp_path: Path) -> None:
    path = write_payload(tmp_path / "state.json", RECEIVED_AT.isoformat())
    now = RECEIVED_AT + timedelta(seconds=100)
    message = (
        "Game state is stale: received 100 s ago (limit 30 s). Is the game running with the mod?"
    )
    with raises_exactly(message):
        load_game_state(path, max_age_seconds=30, now=now)


def test_bad_fake_tower_path_message() -> None:
    with raises_exactly('Tower must be NAME:X-Y-Z, got "Dart Monkey:bad"'):
        fake_tower("Dart Monkey", "bad")


def test_empty_base_id_raises() -> None:
    bad = {"base_id": "", "tiers": [0, 0, 0]}
    with raises_exactly("base_id must be a string"):
        parse_game_state(valid_payload(towers=[bad]))


@pytest.mark.parametrize("key", ["difficulty", "mode"])
def test_empty_required_text_raises(key: str) -> None:
    with raises_exactly(f"{key} must be a string"):
        parse_game_state(valid_payload(**{key: ""}))


def test_non_string_map_raises() -> None:
    with raises_exactly("map must be a string"):
        parse_game_state(valid_payload(map=5))


def test_empty_map_allowed() -> None:
    assert parse_game_state(valid_payload(map="")).map_name == ""


def test_game_id_from_name_strips_spaces() -> None:
    assert game_id_from_name("Dart Monkey") == "DartMonkey"


def test_tower_ids_maps_back_to_name() -> None:
    assert TOWER_IDS["DartMonkey"] == "Dart Monkey"


def test_parse_tower_spec_splits_on_first_colon() -> None:
    assert parse_tower_spec("Dart Monkey:0-2-3:x") == ("Dart Monkey", "0-2-3:x")


def test_naive_received_at_is_utc(tmp_path: Path) -> None:
    path = write_payload(tmp_path / "state.json", "2026-01-01T12:00:00")
    now = datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC)
    stored = load_game_state(path, now=now)
    assert stored.received_at.tzinfo is UTC
    assert stored.received_at == RECEIVED_AT


def test_aware_received_at_keeps_offset(tmp_path: Path) -> None:
    path = write_payload(tmp_path / "state.json", "2026-01-01T17:00:00+05:00")
    now = datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC)
    stored = load_game_state(path, now=now)
    assert stored.received_at.utcoffset() == timedelta(hours=5)
    assert stored.received_at.tzinfo == timezone(timedelta(hours=5))


def test_save_leaves_only_target_file(tmp_path: Path) -> None:
    folder = tmp_path / "sub"
    folder.mkdir()
    target = folder / "state.json"
    save_game_state(target, fake_game_state(5, 100), RECEIVED_AT)
    assert [entry.name for entry in folder.iterdir()] == ["state.json"]


def test_fake_tower_fields() -> None:
    tower = fake_tower("Dart Monkey", "0-0-0")
    assert tower.tower_name == "Dart Monkey"
    assert tower.known is True


@pytest.mark.parametrize(
    ("difficulty", "mode"),
    [
        ("impoppable", "Impoppable"),
        ("easy", "Standard"),
        ("medium", "Standard"),
        ("hard", "Standard"),
    ],
)
def test_fake_game_state_mode(difficulty: str, mode: str) -> None:
    state = fake_game_state(5, 100, difficulty)
    assert state.mode == mode
    assert state.map_name == "Unknown"
