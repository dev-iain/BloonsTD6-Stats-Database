from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6.game_state import (
    DEFAULT_MAX_AGE_SECONDS,
    GameStateError,
    NoGameStateError,
    PlacedTower,
    StaleGameStateError,
    difficulty_from_game,
    load_game_state,
    parse_game_state,
    save_game_state,
    state_to_payload,
    tiers_to_path,
    tower_name_from_game_id,
)

VALID_PATH = Path(__file__).parent / "fixtures" / "game_state" / "valid.json"
RECEIVED_AT = datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 24, 12, 0, 30, tzinfo=UTC)


def valid_payload(**overrides: object) -> dict[str, object]:
    payload = json.loads(VALID_PATH.read_text(encoding="utf-8"))
    payload.update(overrides)
    return payload


def payload_without(key: str) -> dict[str, object]:
    payload = valid_payload()
    del payload[key]
    return payload


def saved_valid_state(path: Path) -> None:
    save_game_state(path, parse_game_state(valid_payload()), RECEIVED_AT)


def test_parse_game_state_all_base():
    state = parse_game_state(valid_payload())
    assert state.round_number == 40
    assert state.money == 5123
    assert state.lives == 150
    assert state.difficulty == "medium"
    assert state.mode == "Standard"
    assert state.map_name == "Monkey Meadow"
    assert state.towers == (
        PlacedTower("DartMonkey", "Dart Monkey", "0-2-3", True),
        PlacedTower("BananaFarm", None, "2-0-0", False),
    )


def test_parse_game_state_unsupported_version():
    with pytest.raises(GameStateError):
        parse_game_state(valid_payload(version=2))


def test_parse_game_state_missing_version():
    with pytest.raises(GameStateError):
        parse_game_state(payload_without("version"))


def test_parse_game_state_round_one():
    assert parse_game_state(valid_payload(round=1)).round_number == 1


@pytest.mark.parametrize(
    "bad_round",
    [
        pytest.param(0, id="test_parse_game_state_round_zero"),
        pytest.param("40", id="test_parse_game_state_round_not_int"),
        pytest.param(True, id="test_parse_game_state_round_boolean"),
    ],
)
def test_parse_game_state_invalid_round(bad_round):
    with pytest.raises(GameStateError):
        parse_game_state(valid_payload(round=bad_round))


def test_parse_game_state_zero_cash():
    assert parse_game_state(valid_payload(cash=0)).money == 0


@pytest.mark.parametrize(
    "bad_cash",
    [
        pytest.param(-1, id="test_parse_game_state_negative_cash"),
        pytest.param("5000", id="test_parse_game_state_cash_not_number"),
    ],
)
def test_parse_game_state_invalid_cash(bad_cash):
    with pytest.raises(GameStateError):
        parse_game_state(valid_payload(cash=bad_cash))


@pytest.mark.parametrize(
    ("difficulty", "mode", "expected"),
    [
        pytest.param("Hard", "Impoppable", "impoppable", id="impoppable"),
        pytest.param("Hard", "CHIMPS", "hard", id="chimps"),
    ],
)
def test_parse_game_state_difficulty_with_mode(difficulty, mode, expected):
    payload = valid_payload(difficulty=difficulty, mode=mode)
    assert parse_game_state(payload).difficulty == expected


def test_parse_game_state_unknown_difficulty():
    with pytest.raises(GameStateError):
        parse_game_state(valid_payload(difficulty="Nightmare"))


def test_parse_game_state_no_towers():
    assert parse_game_state(valid_payload(towers=[])).towers == ()


@pytest.mark.parametrize(
    "bad_towers",
    [
        pytest.param(
            [{"base_id": "DartMonkey", "tiers": [0, 6, 0]}],
            id="test_parse_game_state_tier_out_of_range",
        ),
        pytest.param(
            [{"base_id": "DartMonkey", "tiers": [0, 2]}],
            id="test_parse_game_state_wrong_tier_count",
        ),
        pytest.param("DartMonkey", id="test_parse_game_state_towers_not_list"),
    ],
)
def test_parse_game_state_invalid_towers(bad_towers):
    with pytest.raises(GameStateError):
        parse_game_state(valid_payload(towers=bad_towers))


def test_game_state_error_is_value_error():
    assert issubclass(GameStateError, ValueError)
    assert issubclass(NoGameStateError, GameStateError)
    assert issubclass(StaleGameStateError, GameStateError)


@pytest.mark.parametrize(
    ("base_id", "expected"),
    [
        pytest.param("DartMonkey", "Dart Monkey", id="two_words"),
        pytest.param("Druid", "Druid", id="one_word"),
        pytest.param("BananaFarm", None, id="unknown"),
        pytest.param("Dart Monkey", None, id="database_name"),
    ],
)
def test_tower_name_from_game_id(base_id, expected):
    assert tower_name_from_game_id(base_id) == expected


def test_tiers_to_path_joins_with_dashes():
    assert tiers_to_path([0, 2, 3]) == "0-2-3"


@pytest.mark.parametrize(
    ("difficulty", "mode", "expected"),
    [
        ("Medium", "Standard", "medium"),
        ("hard", "impoppable", "impoppable"),
        ("Hard", "CHIMPS", "hard"),
    ],
)
def test_difficulty_from_game(difficulty, mode, expected):
    assert difficulty_from_game(difficulty, mode) == expected


def test_load_game_state_all_base(tmp_path):
    path = tmp_path / "state.json"
    saved_valid_state(path)
    stored = load_game_state(path, max_age_seconds=60, now=NOW)
    assert stored.state == parse_game_state(valid_payload())
    assert stored.received_at == RECEIVED_AT


def test_load_game_state_missing_file(tmp_path):
    with pytest.raises(NoGameStateError):
        load_game_state(tmp_path / "absent.json", max_age_seconds=60, now=NOW)


def test_load_game_state_invalid_json(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(GameStateError) as raised:
        load_game_state(path, max_age_seconds=60, now=NOW)
    assert not isinstance(raised.value, NoGameStateError)


def test_load_game_state_age_equal_to_limit(tmp_path):
    path = tmp_path / "state.json"
    saved_valid_state(path)
    stored = load_game_state(path, max_age_seconds=30, now=NOW)
    assert stored.state == parse_game_state(valid_payload())


def test_load_game_state_stale(tmp_path):
    path = tmp_path / "state.json"
    saved_valid_state(path)
    with pytest.raises(StaleGameStateError):
        load_game_state(path, max_age_seconds=29, now=NOW)


def test_load_game_state_no_age_check(tmp_path):
    path = tmp_path / "state.json"
    saved_valid_state(path)
    stored = load_game_state(path, max_age_seconds=None, now=NOW)
    assert stored.state == parse_game_state(valid_payload())


def test_default_max_age_seconds_is_thirty():
    assert DEFAULT_MAX_AGE_SECONDS == 30


tower_payloads = st.fixed_dictionaries(
    {
        "base_id": st.sampled_from(["DartMonkey", "SuperMonkey", "Druid", "BananaFarm"]),
        "tiers": st.lists(st.integers(0, 5), min_size=3, max_size=3),
    }
)

valid_payloads = st.fixed_dictionaries(
    {
        "version": st.just(1),
        "round": st.integers(1, 200),
        "cash": st.floats(0, 1e6, allow_nan=False),
        "lives": st.integers(0, 10000),
        "difficulty": st.sampled_from(
            ["Easy", "easy", "EASY", "Medium", "medium", "Hard", "HARD", "hard"]
        ),
        "mode": st.sampled_from(["Standard", "Impoppable", "CHIMPS", "Deflation"]),
        "map": st.text(max_size=20),
        "towers": st.lists(tower_payloads, max_size=8),
    }
)


@given(payload=valid_payloads)
def test_state_to_payload_round_trip(payload):
    state = parse_game_state(payload)
    assert parse_game_state(state_to_payload(state)) == state
