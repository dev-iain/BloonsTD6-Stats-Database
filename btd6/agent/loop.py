from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from btd6.agent.client import AgentError
from btd6.agent.picks import AgentResult, parse_picks
from btd6.agent.schemas import LIVE_TOOL_SCHEMAS, TOOL_SCHEMAS
from btd6.agent.tools import ToolCall, execute_call
from btd6.game_state import PlacedTower

SYSTEM_PROMPT = """\
You are a Bloons TD6 advisor. You only know what the tools return.
1. Call get_round_threats for the round first.
2. Call recommend with the round, money and difficulty to get affordable candidates. \
Use rank_upgrades or search_upgrades only to compare alternatives.
3. Check every pick's cost against the money with total_cost or the cost in the tool result. \
Never pick something that costs more than the money.
4. Explain in a few sentences why the picks fit the round's threats \
(camo, lead, MOAB share, pierce).
Never state a number, tower or upgrade path that did not come from a tool result. \
If a tool returns an error, say so and do not make up data. \
If nothing is affordable, say so plainly.
End the answer with a line "Picks:" followed by one line per pick in the form \
"- <tower name> <X-Y-Z> $<total cost>", or "- none"."""


LIVE_PROMPT = """\
This is a live game. The towers the player already owns are listed in the request; \
call get_game_state if you need the current cash, lives or towers again. \
Mention upgrades to owned towers in the explanation when they fit the round better than a \
new tower, but list only new purchases under Picks."""


class ChatClient(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> dict: ...


def describe_tower(tower: PlacedTower) -> str:
    if tower.known:
        return f"{tower.tower_name} {tower.path}"
    return f"{tower.base_id} {tower.path} (not in the database)"


def owned_towers_text(owned_towers: Sequence[PlacedTower] | None) -> str:
    if owned_towers is None:
        return ""
    if not owned_towers:
        return " You own no towers."
    return " You own: " + ", ".join(describe_tower(tower) for tower in owned_towers) + "."


def opening_messages(
    round_number: int,
    money: int,
    difficulty: str,
    live: bool,
    owned_towers: Sequence[PlacedTower] | None,
) -> list[dict]:
    request = (
        f"Round {round_number}, money ${money}, difficulty {difficulty}."
        f"{owned_towers_text(owned_towers)} Recommend what to buy."
    )
    system = (SYSTEM_PROMPT + "\n" + LIVE_PROMPT) if live else SYSTEM_PROMPT
    return [{"role": "system", "content": system}, {"role": "user", "content": request}]


def run_agent(
    connection: sqlite3.Connection,
    client: ChatClient,
    round_number: int,
    money: int,
    difficulty: str = "medium",
    max_iterations: int = 8,
    state_path: Path | None = None,
    owned_towers: Sequence[PlacedTower] | None = None,
) -> AgentResult:
    live = state_path is not None
    messages = opening_messages(round_number, money, difficulty, live, owned_towers)
    schemas = LIVE_TOOL_SCHEMAS if live else TOOL_SCHEMAS
    records: list[ToolCall] = []
    for _ in range(max_iterations):
        message = client.complete(messages, schemas)
        requested = message.get("tool_calls")
        if not requested:
            answer = message.get("content") or ""
            return AgentResult(answer, tuple(records), parse_picks(answer))
        messages.append(message)
        for call in requested:
            record = execute_call(connection, call, state_path)
            records.append(record)
            content = json.dumps(record.result)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    raise AgentError(f"No final answer after {max_iterations} iterations")
