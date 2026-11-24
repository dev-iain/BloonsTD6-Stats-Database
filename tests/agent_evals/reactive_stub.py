from __future__ import annotations

import json
from typing import Any

from tests.agent_stub import final_message, tool_call_message


def first_recommendation(tool_content: str) -> dict[str, Any] | None:
    recommendations = json.loads(tool_content).get("recommendations") or []
    return recommendations[0] if recommendations else None


class ReactiveStub:
    """Calls get_round_threats then recommend, then answers from what recommend returned."""

    def __init__(self, round_number: int, money: int, difficulty: str = "medium") -> None:
        self.round_number = round_number
        self.money = money
        self.difficulty = difficulty
        self.call_count = 0

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        self.call_count += 1
        if self.call_count == 1:
            return tool_call_message(("get_round_threats", {"round": self.round_number}))
        if self.call_count == 2:
            arguments = {
                "round": self.round_number,
                "money": self.money,
                "difficulty": self.difficulty,
            }
            return tool_call_message(("recommend", arguments))
        return final_message(compose_answer(messages[-1]["content"]))


def compose_answer(tool_content: str) -> str:
    parsed = json.loads(tool_content)
    if "error" in parsed:
        error = parsed["error"]
        return f"The tool returned {error['type']}: {error['message']}\nPicks:\n- none"
    pick = first_recommendation(tool_content)
    if pick is None:
        return "Nothing affordable fits this round.\nPicks:\n- none"
    line = f"- {pick['tower_name']} {pick['path']} ${pick['total_cost']:,}"
    return f"Best fit for the round.\nPicks:\n{line}"
