from __future__ import annotations

import copy
import json
from typing import Any


def tool_call_message(*calls: tuple[str, dict[str, Any] | str], content: str | None = None) -> dict:
    """Assistant message requesting tools; a str argument is sent as the raw arguments string."""
    entries = []
    for position, (name, arguments) in enumerate(calls, 1):
        raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
        entries.append(
            {
                "id": f"call_{position}",
                "type": "function",
                "function": {"name": name, "arguments": raw},
            }
        )
    return {"role": "assistant", "content": content, "tool_calls": entries}


def final_message(text: str) -> dict:
    return {"role": "assistant", "content": text, "tool_calls": None}


class ScriptedClient:
    """ChatClient stub that replays scripted assistant messages and records each request."""

    def __init__(self, script: list[dict], repeat_last: bool = False) -> None:
        self.script = list(script)
        self.repeat_last = repeat_last
        self.requests: list[tuple[list[dict], list[dict]]] = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        self.requests.append((copy.deepcopy(messages), tools))
        position = len(self.requests) - 1
        if position >= len(self.script):
            if not self.repeat_last:
                raise AssertionError("ScriptedClient ran out of scripted messages")
            position = len(self.script) - 1
        return copy.deepcopy(self.script[position])
