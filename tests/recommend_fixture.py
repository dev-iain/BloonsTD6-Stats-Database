from __future__ import annotations

import json
import sqlite3
from typing import Any

from btd6.db import connect
from btd6.db.cost_loader import load_costs
from btd6.db.loader import load_tower
from btd6.db.round_loader import load_bloons, load_rounds
from btd6.db.seed import initialize_database
from btd6.etl.fetch import fetch_costs
from btd6.recommend import Recommendation
from btd6.threats import PROPERTY_NAMES, RoundThreats
from tests.factories import RoundThreatsFactory
from tests.income_fixture import FIXTURES, read_group_rows
from tests.test_ranking import UPGRADE_STATS, build_database

CAMO_ROUND = 101
CAMO_PATHS = {"0-0-4"}
RESOLVED_TOWER_FILES = {
    "Super Monkey": "super_monkey_resolved.json",
    "Alchemist": "alchemist_resolved.json",
    "Druid": "druid_resolved.json",
    "Ninja Monkey": "ninja_resolved.json",
    "Wizard Monkey": "wizard_resolved.json",
    "Dart Monkey": "dart_monkey_resolved_sample.json",
    "Boomerang Monkey": "boomerang_monkey_resolved_sample.json",
    "Bomb Shooter": "bomb_shooter_resolved_sample.json",
    "Sniper Monkey": "sniper_monkey_resolved_sample.json",
    "Ice Monkey": "ice_monkey_resolved_sample.json",
}
MAGIC_TOWERS = {"Super Monkey", "Alchemist", "Druid", "Ninja Monkey", "Wizard Monkey"}


def camo_specs() -> dict[str, dict[str, Any]]:
    return {
        path: {**stats, "can_hit_camo": path in CAMO_PATHS} for path, stats in UPGRADE_STATS.items()
    }


def load_round_data(connection: sqlite3.Connection, with_camo_round: bool = True) -> None:
    load_bloons(connection, json.loads((FIXTURES / "bloon_rows.json").read_text()))
    connection.execute("UPDATE bloons SET has_lead = 1 WHERE name = 'Lead'")
    connection.commit()
    rows = read_group_rows(100)
    if with_camo_round:
        rows.append(
            {
                "round": CAMO_ROUND,
                "group_index": 0,
                "bloon": "BlueCamo",
                "count": 10,
                "start": 0.0,
                "duration": 1.0,
            }
        )
    bloon_ids = {
        row["name"]: row["id"] for row in connection.execute("SELECT id, name FROM bloons")
    }
    load_rounds(connection, rows, bloon_ids)


def build_recommend_database(
    with_costs: bool = True, with_rounds: bool = True
) -> sqlite3.Connection:
    """Four-upgrade Super Monkey database; only `0-0-4` hits camo."""
    connection = build_database(camo_specs(), with_costs=with_costs)
    if with_rounds:
        load_round_data(connection)
    return connection


def build_full_database(rounds: bool = True) -> sqlite3.Connection:
    """Every resolved tower fixture, Super Monkey costs for each, rounds 1-100.

    The caller must use the `offline_costs_wiki` fixture.
    """
    connection = connect(":memory:")
    initialize_database(connection)
    for name, file_name in RESOLVED_TOWER_FILES.items():
        resolved = json.loads((FIXTURES / file_name).read_text())
        category = "Magic" if name in MAGIC_TOWERS else "Primary"
        load_tower(connection, name, resolved, category)
        load_costs(connection, name, fetch_costs(name))
    if rounds:
        load_round_data(connection, with_camo_round=False)
    return connection


MEDIUM_COSTS = {"0-0-0": 2500, "1-0-0": 4500, "3-0-0": 27000, "0-0-4": 67855}
FIXTURE_RANGE = 50
WINDOW_DECAY = 0.75


def make_threats(
    camo_share: float = 0.0,
    lead: float = 0.0,
    moab_share: float = 0.0,
    **shares: float,
) -> RoundThreats:
    property_share = {name: shares.get(name, 0.0) for name in PROPERTY_NAMES}
    property_share["lead"] = lead
    return RoundThreatsFactory.build(
        property_share=property_share, camo_share=camo_share, moab_share=moab_share
    )


def round_density(round_number: int) -> float:
    """Independent oracle for `crowd_density` of a plain (no fortified) fixture round."""
    bloons_by_name = {
        row["name"]: row for row in json.loads((FIXTURES / "bloon_rows.json").read_text())
    }
    weighted = total = 0.0
    for group in read_group_rows(100):
        if group["round"] != round_number:
            continue
        bloon = bloons_by_name[group["bloon"]]
        group_rbe = group["count"] * bloon["rbe"]
        per_second = group["count"] / max(group["duration"], 1.0)
        weighted += group_rbe * per_second / bloon["speed"]
        total += group_rbe
    return weighted / total


def upgrade_dps(path: str) -> float:
    stats = UPGRADE_STATS[path]
    return stats["projectile_count"] * stats["projectile_damage"] / stats["attack_rate"]


def capped_pierce(path: str, density: float) -> float:
    return min(UPGRADE_STATS[path]["projectile_pierce"], max(1.0, density * 2 * FIXTURE_RANGE))


def plain_round_fit(path: str, round_number: int) -> float:
    """Round fit of a Super Monkey upgrade in a round with `moab_share` 0."""
    pierce = capped_pierce(path, round_density(round_number))
    return upgrade_dps(path) * pierce / MEDIUM_COSTS[path]


def plain_window_score(path: str, start: int, horizon: int) -> float:
    """Decay-weighted mean of the round fits over rounds `start .. start + horizon - 1`."""
    offsets = range(horizon)
    weights = [WINDOW_DECAY**offset for offset in offsets]
    fits = [plain_round_fit(path, start + offset) for offset in offsets]
    return sum(weight * round_fit for weight, round_fit in zip(weights, fits, strict=True)) / sum(
        weights
    )


LEAD_PATHS = {"3-0-0", "0-0-4"}
ROUND_NEEDS: dict[int, set[str]] = {24: {"camo"}, 28: {"lead"}, 63: {"lead"}, 101: {"camo"}}
NEED_PATHS = {"camo": CAMO_PATHS, "lead": LEAD_PATHS}


def tiers_of(path: str) -> tuple[int, ...]:
    return tuple(int(tier) for tier in path.split("-"))


def reachable_paths(owned_path: str) -> list[str]:
    """Fixture paths an owned upgrade can be upgraded to: every tier at least as high, not equal."""
    owned_tiers = tiers_of(owned_path)
    return [
        path
        for path in MEDIUM_COSTS
        if path != owned_path
        and all(
            new_tier >= owned_tier
            for new_tier, owned_tier in zip(tiers_of(path), owned_tiers, strict=True)
        )
    ]


def upgrade_price(owned_path: str, path: str) -> int:
    return MEDIUM_COSTS[path] - MEDIUM_COSTS[owned_path]


def fixture_value(path: str, round_number: int, covered: frozenset[str] = frozenset()) -> float:
    """Independent oracle of the per-round value: zero with an unmet need, else dps x pierce.

    Valid for fixture rounds with `moab_share` 0 and a crowd density that `round_density` can
    compute (rounds 1-23, 26-28, 63).
    """
    for need in ROUND_NEEDS.get(round_number, set()) - covered:
        if path not in NEED_PATHS[need]:
            return 0.0
    pierce = capped_pierce(path, round_density(round_number))
    return upgrade_dps(path) * pierce


def upgrade_window_score(
    owned_path: str,
    path: str,
    start: int,
    horizon: int,
    covered: frozenset[str] = frozenset(),
) -> float:
    """Decay-weighted mean of (value(Q) - value(P)) / price over the window."""
    offsets = range(horizon)
    price = upgrade_price(owned_path, path)
    weights = [WINDOW_DECAY**offset for offset in offsets]
    fits = [
        (
            fixture_value(path, start + offset, covered)
            - fixture_value(owned_path, start + offset, covered)
        )
        / price
        for offset in offsets
    ]
    return sum(weight * fit for weight, fit in zip(weights, fits, strict=True)) / sum(weights)


def make_recommendation(
    score: float | None,
    total_cost: int,
    first_leak_round: int | None = None,
    upgrade_from: str | None = None,
) -> Recommendation:
    """A `Recommendation` with only the fields `sort_key` reads set."""
    return Recommendation(
        tower_name="Super Monkey",
        path="0-0-0",
        total_cost=total_cost,
        upgrade_from=upgrade_from,
        score=score,
        dps=None,
        moab_dps=None,
        pierce_weighted_dps=None,
        projectile_pierce=None,
        effective_pierce=None,
        first_leak_round=first_leak_round,
        reasons=(),
    )
