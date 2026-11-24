from __future__ import annotations

import re
from dataclasses import dataclass

from btd6.agent.tools import ToolCall

PICK_PATTERN = re.compile(r"-\s+(.+?)\s+([0-5]-[0-5]-[0-5])\s+\$([\d,]+)")
HEADER = "picks:"


@dataclass(frozen=True)
class Pick:
    tower_name: str
    path: str
    total_cost: int


@dataclass(frozen=True)
class AgentResult:
    answer: str
    tool_calls: tuple[ToolCall, ...]
    picks: tuple[Pick, ...]


def parse_picks(answer: str) -> tuple[Pick, ...]:
    lines = [line.strip() for line in answer.splitlines()]
    headers = [index for index, line in enumerate(lines) if line.lower() == HEADER]
    if not headers:
        return ()
    picks = []
    for line in lines[headers[-1] + 1 :]:
        match = PICK_PATTERN.fullmatch(line)
        if match:
            name, path, cost = match.groups()
            picks.append(Pick(name, path, int(cost.replace(",", ""))))
    return tuple(picks)
