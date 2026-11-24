from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

from btd6.agent.picks import AgentResult, Pick


def walk_dicts(value: Any) -> Iterator[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list | tuple):
        for child in value:
            yield from walk_dicts(child)


def result_rows(result: AgentResult, tool_name: str | None = None) -> list[dict]:
    rows = []
    for call in result.tool_calls:
        if tool_name is None or call.name == tool_name:
            rows.extend(row for row in walk_dicts(call.result) if "path" in row)
    return rows


def find_row(result: AgentResult, pick: Pick) -> dict | None:
    for row in result_rows(result):
        if (row.get("tower_name"), row.get("path")) == (pick.tower_name, pick.path):
            return row
    return None


def picks_grounded(
    scenario_id: str, result: AgentResult, connection: sqlite3.Connection, money: int
) -> list[str]:
    return [
        f"{scenario_id}: pick {pick.tower_name} {pick.path} not in any tool result (ungrounded)"
        for pick in result.picks
        if find_row(result, pick) is None
    ]


def picks_affordable(
    scenario_id: str, result: AgentResult, connection: sqlite3.Connection, money: int
) -> list[str]:
    return [
        f"{scenario_id}: pick {pick.tower_name} {pick.path} costs {pick.total_cost}, "
        f"over budget {money}"
        for pick in result.picks
        if pick.total_cost > money
    ]


def picks_known_towers(
    scenario_id: str, result: AgentResult, connection: sqlite3.Connection, money: int
) -> list[str]:
    known = {row[0] for row in connection.execute("SELECT name FROM towers")}
    return [
        f"{scenario_id}: tower {pick.tower_name!r} is not in the towers table"
        for pick in result.picks
        if pick.tower_name not in known
    ]


def picked_rows(result: AgentResult) -> list[dict]:
    rows = [find_row(result, pick) for pick in result.picks]
    return [row for row in rows if row is not None]


def expect_lead_pierce(result: AgentResult) -> str | None:
    for row in picked_rows(result):
        if "pops_lead" in row.get("reasons", []) and row.get("pierce_weighted_dps") is not None:
            return None
    return "no pick pops lead with a non-null pierce_weighted_dps"


def expect_moab(result: AgentResult) -> str | None:
    if any(row.get("moab_dps") is not None for row in picked_rows(result)):
        return None
    return "no pick has a non-null moab_dps"


def expect_camo(result: AgentResult) -> str | None:
    if any("hits_camo" in row.get("reasons", []) for row in picked_rows(result)):
        return None
    return "no pick hits camo"


def expect_nothing_affordable(result: AgentResult) -> str | None:
    recommends = [call for call in result.tool_calls if call.name == "recommend"]
    if not recommends or recommends[-1].result.get("recommendations") != []:
        return "recommend did not return an empty list"
    if result.picks != ():
        return f"picks should be empty, got {result.picks}"
    return None


def expect_round_data_error(result: AgentResult) -> str | None:
    errors = [
        call.result["error"]["type"]
        for call in result.tool_calls
        if isinstance(call.result.get("error"), dict)
    ]
    if "NoRoundDataError" not in errors:
        return "no NoRoundDataError in any tool result"
    if result.picks != ():
        return f"picks should be empty, got {result.picks}"
    return None


EXPECTATIONS = {
    "lead_pierce": expect_lead_pierce,
    "moab": expect_moab,
    "camo": expect_camo,
    "nothing_affordable": expect_nothing_affordable,
    "round_data_error": expect_round_data_error,
}


def scenario_expectation(
    scenario: dict, result: AgentResult, connection: sqlite3.Connection, money: int
) -> list[str]:
    problem = EXPECTATIONS[scenario["expectation"]](result)
    return [f"{scenario['id']}: {problem}"] if problem else []


def run_all_checks(
    scenario: dict, result: AgentResult, connection: sqlite3.Connection
) -> list[str]:
    money = scenario["money"]
    failures = []
    for check in (picks_grounded, picks_affordable, picks_known_towers):
        failures.extend(check(scenario["id"], result, connection, money))
    failures.extend(scenario_expectation(scenario, result, connection, money))
    return failures
