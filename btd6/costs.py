from __future__ import annotations

import re
import sqlite3
from fractions import Fraction

from btd6.query import QueryError

DIFFICULTY_MULTIPLIERS = {
    "easy": Fraction(85, 100),
    "medium": Fraction(1),
    "hard": Fraction(108, 100),
    "impoppable": Fraction(120, 100),
}
PATH_PATTERN = re.compile(r"[0-9]-[0-9]-[0-9]")
MAX_TIER = 5


def parse_path(path: str) -> list[int]:
    if not PATH_PATTERN.fullmatch(path):
        raise QueryError(f"Malformed upgrade path: {path!r}")
    tiers = [int(part) for part in path.split("-")]
    if max(tiers) > MAX_TIER:
        raise QueryError(f"Tier above {MAX_TIER} in path {path!r}")
    if sum(tier > 0 for tier in tiers) > 2 or sum(tier > 2 for tier in tiers) > 1:
        raise QueryError(f"Invalid crosspath: {path!r}")
    return tiers


def round_price(cost: int, multiplier: Fraction) -> int:
    scaled = (Fraction(cost, 5) - 1) * multiplier
    return 5 * ((scaled + Fraction(1, 2)).__floor__() + 1)


def tier_cost(connection: sqlite3.Connection, tower_id: int, path_index: int, tier: int) -> int:
    row = connection.execute(
        "SELECT cost FROM upgrade_costs WHERE tower_id = ? AND path_index = ? AND tier = ?",
        (tower_id, path_index, tier),
    ).fetchone()
    if row is None:
        raise QueryError(f"Missing cost for path {path_index} tier {tier}")
    return int(row[0])


def total_cost(
    connection: sqlite3.Connection, tower_name: str, path: str, difficulty: str = "medium"
) -> int | None:
    """Total price of `tower_name` at `path`, rounding each price per difficulty."""
    tiers = parse_path(path)
    if difficulty not in DIFFICULTY_MULTIPLIERS:
        raise QueryError(f"Unknown difficulty: {difficulty!r}")
    row = connection.execute(
        "SELECT id, base_cost FROM towers WHERE name = ?", (tower_name,)
    ).fetchone()
    if row is None:
        raise QueryError(f"Unknown tower: {tower_name!r}")
    if row["base_cost"] is None:
        return None
    multiplier = DIFFICULTY_MULTIPLIERS[difficulty]
    prices = [row["base_cost"]]
    for path_index, top_tier in enumerate(tiers, start=1):
        prices += [tier_cost(connection, row["id"], path_index, t) for t in range(1, top_tier + 1)]
    return sum(round_price(price, multiplier) for price in prices)
