from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from btd6.costs import validate_difficulty
from btd6.query import QueryError, UpgradeFilters
from btd6.ranking import rank_upgrades
from btd6.rounds import NoRoundDataError, validate_round
from btd6.threats import PROPERTY_NAMES, RoundThreats, round_threats

MIN_PROPERTY_SHARE = 0.05
HIGH_PIERCE = 5


@dataclass(frozen=True)
class Recommendation:
    tower_name: str
    path: str
    total_cost: int
    score: float | None
    dps: float | None
    moab_dps: float | None
    pierce_weighted_dps: float | None
    projectile_pierce: float | None
    reasons: tuple[str, ...]


def whole_number(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QueryError(f"{name} must be a whole number, got {value!r}")


def validate_inputs(
    connection: sqlite3.Connection,
    round_number: int,
    money: int,
    difficulty: str,
    limit: int | None,
) -> None:
    whole_number("money", money)
    if money < 0:
        raise QueryError(f"money must be 0 or more, got {money}")
    validate_difficulty(difficulty)
    if limit is not None:
        whole_number("limit", limit)
        if limit < 1:
            raise QueryError(f"limit must be at least 1, got {limit}")
    try:
        validate_round(connection, round_number)
    except NoRoundDataError:
        raise
    except (TypeError, ValueError) as error:
        raise QueryError(str(error)) from error


def required_properties(threats: RoundThreats) -> list[str]:
    return [name for name in PROPERTY_NAMES if threats.property_share[name] >= MIN_PROPERTY_SHARE]


def filters_for_threats(threats: RoundThreats) -> UpgradeFilters:
    pop_flags = {f"can_pop_{name}": True for name in required_properties(threats)}
    camo = True if threats.camo_share > 0 else None
    return UpgradeFilters(can_hit_camo=camo, **pop_flags)


def missing(value: float | None) -> bool:
    return value is None or math.isnan(value)


def weighted_term(weight: float, value: float | None) -> float | None:
    if weight == 0:
        return 0.0
    return None if missing(value) else weight * value


def score_terms(
    moab_share: float, moab_dps: float | None, pierce_dps: float | None
) -> tuple[float | None, float | None]:
    return weighted_term(moab_share, moab_dps), weighted_term(1 - moab_share, pierce_dps)


def round_score(
    moab_share: float,
    moab_dps: float | None,
    pierce_dps: float | None,
    total_cost: float | None,
) -> float | None:
    if missing(total_cost) or total_cost == 0:
        return None
    terms = score_terms(moab_share, moab_dps, pierce_dps)
    if None in terms:
        return None
    return sum(terms) / total_cost


def reasons_for(
    threats: RoundThreats,
    moab_dps: float | None,
    pierce_dps: float | None,
    projectile_pierce: float | None,
) -> tuple[str, ...]:
    reasons = ["affordable"]
    if threats.camo_share > 0:
        reasons.append("hits_camo")
    reasons.extend(f"pops_{name}" for name in required_properties(threats))
    moab_term, pierce_term = (
        term or 0.0 for term in score_terms(threats.moab_share, moab_dps, pierce_dps)
    )
    if pierce_term > moab_term and not missing(projectile_pierce):
        if projectile_pierce >= HIGH_PIERCE:
            reasons.append("high_pierce")
    elif moab_term > pierce_term:
        reasons.append("high_single_target")
    return tuple(reasons)


def optional_float(value: float | None) -> float | None:
    return None if missing(value) else float(value)


def to_recommendation(row: dict, threats: RoundThreats) -> Recommendation:
    moab_dps = optional_float(row["moab_dps"])
    pierce_dps = optional_float(row["pierce_weighted_dps"])
    pierce = optional_float(row["projectile_pierce"])
    return Recommendation(
        tower_name=row["tower_name"],
        path=row["path"],
        total_cost=int(row["total_cost"]),
        score=round_score(threats.moab_share, moab_dps, pierce_dps, row["total_cost"]),
        dps=optional_float(row["dps"]),
        moab_dps=moab_dps,
        pierce_weighted_dps=pierce_dps,
        projectile_pierce=pierce,
        reasons=reasons_for(threats, moab_dps, pierce_dps, pierce),
    )


def sort_key(item: Recommendation) -> tuple:
    score_key = (1, 0.0) if item.score is None else (0, -item.score)
    return (*score_key, item.total_cost, item.tower_name, item.path)


def recommend(
    connection: sqlite3.Connection,
    round_number: int,
    money: int,
    difficulty: str = "medium",
    limit: int | None = None,
) -> list[Recommendation]:
    validate_inputs(connection, round_number, money, difficulty, limit)
    threats = round_threats(connection, round_number)
    frame = rank_upgrades(connection, filters_for_threats(threats), difficulty=difficulty)
    affordable = frame[frame["total_cost"] <= money]
    results = [to_recommendation(row, threats) for row in affordable.to_dict("records")]
    results.sort(key=sort_key)
    return results if limit is None else results[:limit]
