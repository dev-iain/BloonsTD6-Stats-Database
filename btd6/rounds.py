from __future__ import annotations

import sqlite3
from dataclasses import dataclass

NO_ROUND_DATA_MESSAGE = "No round data loaded"

GROUP_SQL = """
SELECT round_groups.group_index, bloons.name, round_groups.is_camo, round_groups.is_regrow,
       round_groups.is_fortified, round_groups.count, round_groups.start,
       round_groups.duration, bloons.rbe, bloons.is_moab
FROM round_groups
JOIN bloons ON bloons.id = round_groups.bloon_id
WHERE round_groups.round = ?
ORDER BY round_groups.group_index
"""


class NoRoundDataError(ValueError):
    """Raised when the rounds table is empty."""


@dataclass(frozen=True)
class RoundGroup:
    group_index: int
    bloon: str
    is_camo: bool
    is_regrow: bool
    is_fortified: bool
    count: int
    start: float
    duration: float
    rbe: int | None
    is_moab: bool


@dataclass(frozen=True)
class RoundSummary:
    round: int
    total_bloons: int
    total_rbe: int
    has_moab: bool
    has_camo: bool
    has_lead: bool
    has_ceramic: bool


def validate_round(connection: sqlite3.Connection, round_number: int) -> None:
    if isinstance(round_number, bool) or not isinstance(round_number, int):
        raise TypeError(f"round_number must be an int, got {type(round_number).__name__}")
    highest = connection.execute("SELECT MAX(round) FROM rounds").fetchone()[0]
    if highest is None:
        raise NoRoundDataError(NO_ROUND_DATA_MESSAGE)
    if round_number < 1 or round_number > highest:
        raise ValueError(f"Round {round_number} is not loaded; loaded rounds are 1-{highest}")


def row_to_group(row: sqlite3.Row | tuple) -> RoundGroup:
    return RoundGroup(
        group_index=row[0],
        bloon=row[1],
        is_camo=bool(row[2]),
        is_regrow=bool(row[3]),
        is_fortified=bool(row[4]),
        count=row[5],
        start=row[6],
        duration=row[7],
        rbe=row[8],
        is_moab=bool(row[9]),
    )


def get_round(connection: sqlite3.Connection, round_number: int) -> list[RoundGroup]:
    validate_round(connection, round_number)
    return [row_to_group(row) for row in connection.execute(GROUP_SQL, (round_number,))]


def get_round_summary(connection: sqlite3.Connection, round_number: int) -> RoundSummary:
    groups = get_round(connection, round_number)
    names = {group.bloon for group in groups}
    return RoundSummary(
        round=round_number,
        total_bloons=sum(group.count for group in groups),
        total_rbe=sum(group.count * (group.rbe or 0) for group in groups),
        has_moab=any(group.is_moab for group in groups),
        has_camo=any(group.is_camo for group in groups),
        has_lead="Lead" in names,
        has_ceramic="Ceramic" in names,
    )
