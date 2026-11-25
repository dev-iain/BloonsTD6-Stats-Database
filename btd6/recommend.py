from __future__ import annotations

import math
import re
import sqlite3
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple

from btd6.costs import validate_difficulty
from btd6.query import QueryError, UpgradeFilters
from btd6.ranking import rank_upgrades
from btd6.rounds import NoRoundDataError, validate_round
from btd6.threats import PROPERTY_NAMES, RoundThreats, round_threats

MIN_PROPERTY_SHARE = 0.05
HIGH_PIERCE = 5
DEFAULT_HORIZON = 5
HORIZON_DECAY = 0.75


PATH_PATTERN = re.compile(r"[0-5]-[0-5]-[0-5]")
OWNED_PATTERN = re.compile(r"(.+?)\s+(\d-\d-\d)")


class OwnedTower(NamedTuple):
    tower_name: str
    path: str


@dataclass(frozen=True)
class Recommendation:
    tower_name: str
    path: str
    total_cost: int
    upgrade_from: str | None
    score: float | None
    dps: float | None
    moab_dps: float | None
    pierce_weighted_dps: float | None
    projectile_pierce: float | None
    effective_pierce: float | None
    first_leak_round: int | None
    reasons: tuple[str, ...]


def whole_number(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QueryError(f"{name} must be a whole number, got {value!r}")


def validate_owned(owned: Sequence[OwnedTower]) -> None:
    for entry in owned:
        if not PATH_PATTERN.fullmatch(entry.path):
            raise QueryError(f"owned path must be X-Y-Z, got {entry.path!r}")


def validate_inputs(
    connection: sqlite3.Connection,
    round_number: int,
    money: int,
    difficulty: str,
    limit: int | None,
    horizon: int,
    owned: Sequence[OwnedTower] = (),
    one_per_tower: object = False,
) -> None:
    whole_number("money", money)
    if money < 0:
        raise QueryError(f"money must be 0 or more, got {money}")
    validate_difficulty(difficulty)
    if limit is not None:
        whole_number("limit", limit)
        if limit < 1:
            raise QueryError(f"limit must be at least 1, got {limit}")
    whole_number("horizon", horizon)
    if horizon < 1:
        raise QueryError(f"horizon must be at least 1, got {horizon}")
    validate_owned(owned)
    if not isinstance(one_per_tower, bool):
        raise QueryError(f"one_per_tower must be true or false, got {one_per_tower!r}")
    validate_round_number(connection, round_number)


def validate_round_number(connection: sqlite3.Connection, round_number: int) -> None:
    try:
        validate_round(connection, round_number)
    except NoRoundDataError:
        raise
    except (TypeError, ValueError) as error:
        raise QueryError(str(error)) from error


def parse_owned(text: str) -> OwnedTower:
    match = OWNED_PATTERN.fullmatch(text) if isinstance(text, str) else None
    if match is None:
        raise QueryError(f"owned must be '<tower name> X-Y-Z', got {text!r}")
    return OwnedTower(match.group(1), match.group(2))


def required_properties(threats: RoundThreats, covered: Collection[str] = frozenset()) -> list[str]:
    return [
        name
        for name in PROPERTY_NAMES
        if threats.property_share[name] >= MIN_PROPERTY_SHARE and name not in covered
    ]


def filters_for_threats(
    threats: RoundThreats, covered: Collection[str] | None = None
) -> UpgradeFilters:
    covered = frozenset(covered or ())
    pop_flags = {f"can_pop_{name}": True for name in required_properties(threats, covered)}
    needs_camo = threats.camo_share > 0 and "camo" not in covered
    return UpgradeFilters(can_hit_camo=True if needs_camo else None, **pop_flags)


def missing(value: float | None) -> bool:
    return value is None or math.isnan(value)


def effective_pierce(
    pierce: float | None, range_value: float | None, density: float | None
) -> float | None:
    if missing(pierce):
        return None
    if missing(range_value) or density is None:
        return pierce
    return min(pierce, max(1.0, density * 2 * range_value))


def need_names(threats: RoundThreats, covered: Collection[str] = frozenset()) -> list[str]:
    camo = ["camo"] if threats.camo_share > 0 and "camo" not in covered else []
    return camo + required_properties(threats, covered)


def need_flag(need: str) -> str:
    return "can_hit_camo" if need == "camo" else f"can_pop_{need}"


def unmet_needs(
    row: Mapping[str, Any], threats: RoundThreats, covered: Collection[str] = frozenset()
) -> tuple[str, ...]:
    return tuple(need for need in need_names(threats, covered) if not row[need_flag(need)])


def weighted_term(weight: float, value: float | None) -> float | None:
    if weight == 0:
        return 0.0
    return None if missing(value) else weight * value


def pierce_value(dps: float | None, pierce: float | None) -> float | None:
    return None if missing(dps) or missing(pierce) else dps * pierce


def score_terms(
    moab_share: float, moab_dps: float | None, dps: float | None, pierce: float | None
) -> tuple[float | None, float | None]:
    return (
        weighted_term(moab_share, moab_dps),
        weighted_term(1 - moab_share, pierce_value(dps, pierce)),
    )


def round_score(
    moab_share: float,
    moab_dps: float | None,
    dps: float | None,
    effective_pierce: float | None,
    total_cost: float | None,
) -> float | None:
    if missing(total_cost) or total_cost == 0:
        return None
    terms = score_terms(moab_share, moab_dps, dps, effective_pierce)
    if None in terms:
        return None
    return sum(terms) / total_cost


def reasons_for(
    threats: RoundThreats,
    moab_dps: float | None,
    dps: float | None,
    effective_pierce: float | None,
    covered: Collection[str] = frozenset(),
) -> tuple[str, ...]:
    reasons = ["affordable"]
    if threats.camo_share > 0 and "camo" not in covered:
        reasons.append("hits_camo")
    reasons.extend(f"pops_{name}" for name in required_properties(threats, covered))
    moab_term, pierce_term = (
        term or 0.0 for term in score_terms(threats.moab_share, moab_dps, dps, effective_pierce)
    )
    if pierce_term > moab_term and not missing(effective_pierce):
        if effective_pierce >= HIGH_PIERCE:
            reasons.append("high_pierce")
    elif moab_term > pierce_term:
        reasons.append("high_single_target")
    return tuple(reasons)


def optional_float(value: float | None) -> float | None:
    return None if missing(value) else float(value)


def row_effective_pierce(row: Mapping[str, Any], density: float | None) -> float | None:
    return effective_pierce(
        optional_float(row["projectile_pierce"]), optional_float(row["range"]), density
    )


def row_value(
    row: Mapping[str, Any], threats: RoundThreats, covered: Collection[str]
) -> float | None:
    if unmet_needs(row, threats, covered):
        return 0.0
    terms = score_terms(
        threats.moab_share,
        optional_float(row["moab_dps"]),
        optional_float(row["dps"]),
        row_effective_pierce(row, threats.crowd_density),
    )
    return None if None in terms else sum(terms)


def window_fit(
    row: Mapping[str, Any], threats: RoundThreats, covered: Collection[str] = frozenset()
) -> float | None:
    value = row_value(row, threats, covered)
    cost = row["total_cost"]
    if value is None or missing(cost) or cost == 0:
        return None
    return value / cost


def weighted_mean(fits: list[float | None], window: list[RoundThreats], start: int) -> float | None:
    if None in fits:
        return None
    weights = [HORIZON_DECAY ** (threats.round - start) for threats in window]
    return sum(weight * fit_score for weight, fit_score in zip(weights, fits, strict=True)) / sum(
        weights
    )


def window_score(
    row: Mapping[str, Any],
    window: list[RoundThreats],
    round_number: int,
    covered: Collection[str] = frozenset(),
) -> float | None:
    fits = [window_fit(row, threats, covered) for threats in window]
    return weighted_mean(fits, window, round_number)


def upgrade_fit(
    target: Mapping[str, Any],
    origin: Mapping[str, Any],
    price: int,
    threats: RoundThreats,
    covered: Collection[str],
) -> float | None:
    target_value = row_value(target, threats, covered)
    origin_value = row_value(origin, threats, covered)
    if target_value is None or origin_value is None or price == 0:
        return None
    return (target_value - origin_value) / price


def upgrade_score(
    target: Mapping[str, Any],
    origin: Mapping[str, Any],
    price: int,
    window: list[RoundThreats],
    covered: Collection[str],
) -> float | None:
    fits = [upgrade_fit(target, origin, price, threats, covered) for threats in window]
    return weighted_mean(fits, window, window[0].round)


def leak_reasons(
    row: Mapping[str, Any], window: list[RoundThreats], covered: Collection[str] = frozenset()
) -> list[tuple[int, int, str]]:
    first: dict[str, int] = {}
    for threats in window:
        for need in unmet_needs(row, threats, covered):
            first.setdefault(need, threats.round)
    order = {name: index for index, name in enumerate(("camo", *PROPERTY_NAMES))}
    return sorted((round_at, order[need], need) for need, round_at in first.items())


def reason_codes(
    current: RoundThreats,
    figures: tuple[float | None, float | None, float | None],
    covered: Collection[str],
    origin_path: str | None,
    leaks: list[tuple[int, int, str]],
) -> tuple[str, ...]:
    codes = list(reasons_for(current, *figures, covered))
    if origin_path is not None:
        codes.insert(1, "upgrades_owned")
    fails = [f"fails_{need}_at_{round_at}" for round_at, _, need in leaks]
    return tuple(codes + fails)


def to_recommendation(
    row: Mapping[str, Any],
    window: list[RoundThreats],
    covered: Collection[str],
    score: float | None,
    price: int,
    origin_path: str | None = None,
) -> Recommendation:
    current = window[0]
    leaks = leak_reasons(row, window, covered)
    moab_dps = optional_float(row["moab_dps"])
    dps = optional_float(row["dps"])
    pierce = row_effective_pierce(row, current.crowd_density)
    codes = reason_codes(current, (moab_dps, dps, pierce), covered, origin_path, leaks)
    return Recommendation(
        tower_name=row["tower_name"],
        path=row["path"],
        total_cost=price,
        upgrade_from=origin_path,
        score=score,
        dps=dps,
        moab_dps=moab_dps,
        pierce_weighted_dps=optional_float(row["pierce_weighted_dps"]),
        projectile_pierce=optional_float(row["projectile_pierce"]),
        effective_pierce=pierce,
        first_leak_round=min((round_at for round_at, _, _ in leaks), default=None),
        reasons=codes,
    )


def window_rounds(
    connection: sqlite3.Connection, round_number: int, horizon: int
) -> list[RoundThreats]:
    rows = connection.execute(
        "SELECT round FROM rounds WHERE round BETWEEN ? AND ? ORDER BY round",
        (round_number, round_number + horizon - 1),
    ).fetchall()
    return [round_threats(connection, row[0]) for row in rows]


def sort_key(item: Recommendation) -> tuple:
    score_key = (1, 0.0) if item.score is None else (0, -item.score)
    leaks = item.first_leak_round is not None
    return (
        leaks,
        *score_key,
        item.total_cost,
        item.tower_name,
        item.path,
        item.upgrade_from is not None,
    )


def known_owned_rows(
    connection: sqlite3.Connection, owned: Sequence[OwnedTower], difficulty: str
) -> dict[tuple[str, str], dict[str, Any]]:
    wanted = set(owned)
    known: dict[tuple[str, str], dict[str, Any]] = {}
    for tower_name in sorted({entry.tower_name for entry in wanted}):
        frame = rank_upgrades(
            connection, UpgradeFilters(tower_name=tower_name), difficulty=difficulty
        )
        for row in frame.to_dict("records"):
            if (tower_name, row["path"]) in wanted:
                known[(tower_name, row["path"])] = row
    return known


def covered_needs(known: Collection[Mapping[str, Any]]) -> frozenset[str]:
    needs = ("camo", *PROPERTY_NAMES)
    return frozenset(need for need in needs if any(row[need_flag(need)] for row in known))


def path_tiers(path: str) -> tuple[int, ...]:
    return tuple(int(tier) for tier in path.split("-"))


def reaches(origin_path: str, target_path: str) -> bool:
    pairs = zip(path_tiers(origin_path), path_tiers(target_path), strict=True)
    return origin_path != target_path and all(
        lower_tier <= higher_tier for lower_tier, higher_tier in pairs
    )


def upgrade_price(origin: Mapping[str, Any], target: Mapping[str, Any]) -> int | None:
    if missing(origin["total_cost"]) or missing(target["total_cost"]):
        return None
    return int(target["total_cost"]) - int(origin["total_cost"])


def upgrade_results(
    frame_rows: list[dict[str, Any]],
    known: Mapping[tuple[str, str], Mapping[str, Any]],
    window: list[RoundThreats],
    covered: frozenset[str],
    money: int,
) -> list[Recommendation]:
    results = []
    for (tower_name, origin_path), origin in sorted(known.items()):
        for row in frame_rows:
            if row["tower_name"] != tower_name or not reaches(origin_path, row["path"]):
                continue
            price = upgrade_price(origin, row)
            if price is None or price > money:
                continue
            score = upgrade_score(row, origin, price, window, covered)
            results.append(to_recommendation(row, window, covered, score, price, origin_path))
    return results


def purchase_results(
    frame_rows: list[dict[str, Any]],
    window: list[RoundThreats],
    covered: frozenset[str],
    money: int,
) -> list[Recommendation]:
    affordable = [row for row in frame_rows if row["total_cost"] <= money]
    return [
        to_recommendation(
            row,
            window,
            covered,
            window_score(row, window, window[0].round, covered),
            int(row["total_cost"]),
        )
        for row in affordable
    ]


def first_per_tower(results: list[Recommendation]) -> list[Recommendation]:
    seen: set[str] = set()
    kept = []
    for result in results:
        if result.tower_name not in seen:
            seen.add(result.tower_name)
            kept.append(result)
    return kept


def recommend(
    connection: sqlite3.Connection,
    round_number: int,
    money: int,
    difficulty: str = "medium",
    limit: int | None = None,
    horizon: int = DEFAULT_HORIZON,
    owned: Sequence[OwnedTower] | None = None,
    one_per_tower: bool = False,
) -> list[Recommendation]:
    owned = () if owned is None else owned
    validate_inputs(
        connection, round_number, money, difficulty, limit, horizon, owned, one_per_tower
    )
    known = known_owned_rows(connection, owned, difficulty)
    covered = covered_needs(list(known.values()))
    window = window_rounds(connection, round_number, horizon)
    frame = rank_upgrades(
        connection, filters_for_threats(window[0], covered), difficulty=difficulty
    )
    rows = frame.to_dict("records")
    results = purchase_results(rows, window, covered, money)
    results += upgrade_results(rows, known, window, covered, money)
    results.sort(key=sort_key)
    if one_per_tower:
        results = first_per_tower(results)
    return results if limit is None else results[:limit]
