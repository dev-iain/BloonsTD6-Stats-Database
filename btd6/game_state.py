from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from btd6.costs import DIFFICULTY_MULTIPLIERS, parse_path
from btd6.etl.towers import KNOWN_TOWERS
from btd6.query import QueryError

DEFAULT_MAX_AGE_SECONDS = 30
SUPPORTED_VERSION = 1
GAME_DIFFICULTIES = ("easy", "medium", "hard")
MISSING_STATE_MESSAGE = (
    'No game state at {path}. Start the game with the mod and "python -m btd6 serve", '
    'or run "python -m btd6 fake-state".'
)
DEFAULT_LIVES = 150


def game_id_from_name(tower_name: str) -> str:
    return tower_name.replace(" ", "")


TOWER_IDS: dict[str, str] = {game_id_from_name(name): name for name in KNOWN_TOWERS}


class GameStateError(ValueError):
    pass


class NoGameStateError(GameStateError):
    pass


class StaleGameStateError(GameStateError):
    pass


@dataclass(frozen=True)
class PlacedTower:
    base_id: str
    tower_name: str | None
    path: str
    known: bool


@dataclass(frozen=True)
class GameState:
    round_number: int
    money: int
    lives: int
    difficulty: str
    mode: str
    map_name: str
    towers: tuple[PlacedTower, ...]


@dataclass(frozen=True)
class StoredGameState:
    state: GameState
    received_at: datetime


def tower_name_from_game_id(base_id: str) -> str | None:
    return TOWER_IDS.get(base_id)


def path_to_tiers(path: str) -> list[int]:
    return [int(tier) for tier in path.split("-")]


def tiers_to_path(tiers: Sequence[int]) -> str:
    return "-".join(str(tier) for tier in tiers)


def difficulty_from_game(difficulty: str, mode: str) -> str:
    if mode.lower() == "impoppable":
        return "impoppable"
    return difficulty.lower()


def read_key(payload: Mapping[str, object], key: str) -> object:
    if key not in payload:
        raise GameStateError(f"Missing key: {key}")
    return payload[key]


def read_int(payload: Mapping[str, object], key: str, minimum: int) -> int:
    value = read_key(payload, key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GameStateError(f"{key} must be an integer >= {minimum}")
    return value


def read_whole_number(payload: Mapping[str, object], key: str) -> int:
    value = read_key(payload, key)
    is_number = isinstance(value, int | float) and not isinstance(value, bool)
    if not is_number or not math.isfinite(value) or value < 0:
        raise GameStateError(f"{key} must be a number >= 0")
    return math.floor(value)


def read_text(payload: Mapping[str, object], key: str, allow_empty: bool) -> str:
    value = read_key(payload, key)
    if not isinstance(value, str) or not (value or allow_empty):
        raise GameStateError(f"{key} must be a string")
    return value


def parse_tower(item: object) -> PlacedTower:
    if not isinstance(item, Mapping):
        raise GameStateError("Each tower must be an object")
    base_id = read_text(item, "base_id", allow_empty=False)
    tiers = read_key(item, "tiers")
    valid_tiers = isinstance(tiers, list) and len(tiers) == 3
    if not valid_tiers or not all(
        isinstance(tier, int) and not isinstance(tier, bool) and 0 <= tier <= 5 for tier in tiers
    ):
        raise GameStateError("tiers must be three integers from 0 to 5")
    name = tower_name_from_game_id(base_id)
    return PlacedTower(base_id, name, tiers_to_path(tiers), name is not None)


def parse_towers(value: object) -> tuple[PlacedTower, ...]:
    if not isinstance(value, list):
        raise GameStateError("towers must be a list")
    return tuple(parse_tower(item) for item in value)


def parse_game_state(payload: Mapping[str, object]) -> GameState:
    if read_key(payload, "version") != SUPPORTED_VERSION:
        raise GameStateError(f"Unsupported version: {payload['version']!r}")
    difficulty = read_text(payload, "difficulty", allow_empty=False)
    if difficulty.lower() not in GAME_DIFFICULTIES:
        raise GameStateError(f"Unknown difficulty: {difficulty!r}")
    mode = read_text(payload, "mode", allow_empty=False)
    return GameState(
        round_number=read_int(payload, "round", 1),
        money=read_whole_number(payload, "cash"),
        lives=read_whole_number(payload, "lives"),
        difficulty=difficulty_from_game(difficulty, mode),
        mode=mode,
        map_name=read_text(payload, "map", allow_empty=True),
        towers=parse_towers(read_key(payload, "towers")),
    )


def state_to_payload(state: GameState) -> dict[str, object]:
    difficulty = "hard" if state.difficulty == "impoppable" else state.difficulty
    return {
        "version": SUPPORTED_VERSION,
        "round": state.round_number,
        "cash": state.money,
        "lives": state.lives,
        "difficulty": difficulty.capitalize(),
        "mode": state.mode,
        "map": state.map_name,
        "towers": [
            {"base_id": tower.base_id, "tiers": path_to_tiers(tower.path)} for tower in state.towers
        ],
    }


def save_game_state(path: Path, state: GameState, received_at: datetime) -> None:
    payload = {**state_to_payload(state), "received_at": received_at.isoformat()}
    handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
        json.dump(payload, temp_file)
    os.replace(temp_name, path)


def read_received_at(payload: Mapping[str, object]) -> datetime:
    try:
        received_at = datetime.fromisoformat(str(read_key(payload, "received_at")))
    except ValueError as error:
        raise GameStateError("received_at is not an ISO 8601 timestamp") from error
    return received_at if received_at.tzinfo else received_at.replace(tzinfo=UTC)


def read_state_file(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise NoGameStateError(MISSING_STATE_MESSAGE.format(path=path)) from error
    except json.JSONDecodeError as error:
        raise GameStateError(f"Game state file {path} is not valid JSON") from error
    if not isinstance(payload, dict):
        raise GameStateError(f"Game state file {path} must hold a JSON object")
    return payload


def load_game_state(
    path: Path,
    max_age_seconds: float | None = DEFAULT_MAX_AGE_SECONDS,
    now: datetime | None = None,
) -> StoredGameState:
    payload = read_state_file(path)
    received_at = read_received_at(payload)
    age_seconds = ((now or datetime.now(UTC)) - received_at).total_seconds()
    if max_age_seconds is not None and age_seconds > max_age_seconds:
        raise StaleGameStateError(
            f"Game state is stale: received {age_seconds:.0f} s ago (limit {max_age_seconds:g} s). "
            "Is the game running with the mod?"
        )
    return StoredGameState(parse_game_state(payload), received_at)


def tower_summary(tower: PlacedTower) -> dict[str, object]:
    return {
        "base_id": tower.base_id,
        "tower_name": tower.tower_name,
        "path": tower.path,
        "known": tower.known,
    }


def state_summary(
    stored: StoredGameState,
    now: datetime,
    max_age_seconds: float | None = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, object]:
    state = stored.state
    age_seconds = (now - stored.received_at).total_seconds()
    return {
        "round": state.round_number,
        "money": state.money,
        "lives": state.lives,
        "difficulty": state.difficulty,
        "mode": state.mode,
        "map": state.map_name,
        "towers": [tower_summary(tower) for tower in state.towers],
        "received_at": stored.received_at.isoformat(),
        "age_seconds": age_seconds,
        "stale": max_age_seconds is not None and age_seconds > max_age_seconds,
    }


def parse_tower_spec(spec: str) -> tuple[str, str]:
    name, separator, path = spec.partition(":")
    if not separator or not name:
        raise GameStateError(f'Tower must be NAME:X-Y-Z, got "{spec}"')
    return name, path


def fake_tower(tower_name: str, path: str) -> PlacedTower:
    if tower_name not in KNOWN_TOWERS:
        raise GameStateError(f'Unknown tower "{tower_name}"')
    try:
        parse_path(path)
    except QueryError as error:
        raise GameStateError(f'Tower must be NAME:X-Y-Z, got "{tower_name}:{path}"') from error
    return PlacedTower(game_id_from_name(tower_name), tower_name, path, True)


def fake_game_state(
    round_number: int,
    money: int,
    difficulty: str = "medium",
    towers: Sequence[tuple[str, str]] | None = None,
) -> GameState:
    if difficulty not in DIFFICULTY_MULTIPLIERS:
        raise GameStateError(f"Unknown difficulty: {difficulty!r}")
    placed = tuple(fake_tower(name, path) for name, path in towers or [])
    mode = "Impoppable" if difficulty == "impoppable" else "Standard"
    return GameState(round_number, money, DEFAULT_LIVES, difficulty, mode, "Unknown", placed)
