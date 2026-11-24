from __future__ import annotations

import json
import sqlite3
from typing import Protocol

from btd6.agent.client import AgentError
from btd6.agent.picks import AgentResult, parse_picks
from btd6.agent.schemas import TOOL_SCHEMAS
from btd6.agent.tools import ToolCall, execute_call

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


class ChatClient(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> dict: ...


def run_agent(
    connection: sqlite3.Connection,
    client: ChatClient,
    round_number: int,
    money: int,
    difficulty: str = "medium",
    max_iterations: int = 8,
) -> AgentResult:
    request = (
        f"Round {round_number}, money ${money}, difficulty {difficulty}. Recommend what to buy."
    )
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": request},
    ]
    records: list[ToolCall] = []
    for _ in range(max_iterations):
        message = client.complete(messages, TOOL_SCHEMAS)
        requested = message.get("tool_calls")
        if not requested:
            answer = message.get("content") or ""
            return AgentResult(answer, tuple(records), parse_picks(answer))
        messages.append(message)
        for call in requested:
            record = execute_call(connection, call)
            records.append(record)
            content = json.dumps(record.result)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    raise AgentError(f"No final answer after {max_iterations} iterations")
