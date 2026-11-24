from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from btd6.etl.extract import BLOON_FLAG_COLUMNS, BLOON_PROPERTIES
from btd6.rounds import validate_round

PROPERTY_NAMES = tuple(name.lower() for name in BLOON_PROPERTIES)
THREAT_SQL = f"""
SELECT round_groups.count, round_groups.is_camo, round_groups.is_regrow,
       round_groups.is_fortified, bloons.rbe, bloons.rbe_fort, bloons.layers,
       bloons.is_moab, {", ".join(f"bloons.{column}" for column in BLOON_FLAG_COLUMNS)}
FROM round_groups
JOIN bloons ON bloons.id = round_groups.bloon_id
WHERE round_groups.round = ?
ORDER BY round_groups.group_index
"""


@dataclass(frozen=True)
class RoundThreats:
    round: int
    total_rbe: int
    unknown_groups: int
    property_share: dict[str, float]
    camo_share: float
    regrow_share: float
    moab_share: float
    mean_layers: float


@dataclass(frozen=True)
class GroupWeight:
    rbe: int
    layers: int
    is_camo: bool
    is_regrow: bool
    is_moab: bool
    properties: frozenset[str]


def group_weight(row: sqlite3.Row) -> GroupWeight | None:
    rbe_fort = row["rbe_fort"]
    each = rbe_fort if row["is_fortified"] and rbe_fort is not None else row["rbe"]
    if each is None:
        return None
    return GroupWeight(
        rbe=row["count"] * each,
        layers=row["layers"] or 0,
        is_camo=bool(row["is_camo"]),
        is_regrow=bool(row["is_regrow"]),
        is_moab=bool(row["is_moab"]),
        properties=frozenset(name for name in PROPERTY_NAMES if row[f"has_{name}"]),
    )


def share_of(
    weights: list[GroupWeight], total_rbe: int, matches: Callable[[GroupWeight], bool]
) -> float:
    if total_rbe == 0:
        return 0.0
    return sum(weight.rbe for weight in weights if matches(weight)) / total_rbe


def carries_property(name: str) -> Callable[[GroupWeight], bool]:
    return lambda weight: name in weight.properties


def mean_layers(weights: list[GroupWeight], total_rbe: int) -> float:
    if total_rbe == 0:
        return 0.0
    return sum(weight.rbe * weight.layers for weight in weights) / total_rbe


def round_threats(connection: sqlite3.Connection, round_number: int) -> RoundThreats:
    """Summarise what a round demands: shares of RBE per property, camo, regrow and MOAB.

    Formulas and the pop rule are in `docs/threats.md`.
    """
    validate_round(connection, round_number)
    parsed = [group_weight(row) for row in connection.execute(THREAT_SQL, (round_number,))]
    weights = [weight for weight in parsed if weight is not None]
    total_rbe = sum(weight.rbe for weight in weights)
    return RoundThreats(
        round=round_number,
        total_rbe=total_rbe,
        unknown_groups=len(parsed) - len(weights),
        property_share={
            name: share_of(weights, total_rbe, carries_property(name)) for name in PROPERTY_NAMES
        },
        camo_share=share_of(weights, total_rbe, lambda weight: weight.is_camo),
        regrow_share=share_of(weights, total_rbe, lambda weight: weight.is_regrow),
        moab_share=share_of(weights, total_rbe, lambda weight: weight.is_moab),
        mean_layers=mean_layers(weights, total_rbe),
    )
