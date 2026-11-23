from __future__ import annotations

import sqlite3

import pandas

from btd6.costs import DIFFICULTY_MULTIPLIERS, total_cost
from btd6.query import QueryError, UpgradeFilters, search_upgrades

METRICS = ("dps", "damage_per_dollar", "pierce_damage_per_dollar")
INPUT_COLUMNS = (
    "tower_name",
    "path",
    "projectile_damage",
    "projectile_count",
    "attack_rate",
    "projectile_pierce",
)


def numeric_column(frame: pandas.DataFrame, name: str) -> pandas.Series:
    return pandas.to_numeric(frame[name], errors="coerce").astype(float)


def add_metrics(dataframe: pandas.DataFrame) -> pandas.DataFrame:
    result = dataframe.copy()
    damage = numeric_column(result, "projectile_damage")
    count = numeric_column(result, "projectile_count").fillna(1.0)
    rate = numeric_column(result, "attack_rate").where(lambda series: series != 0)
    cost = numeric_column(result, "total_cost").where(lambda series: series != 0)
    result["dps"] = damage * count / rate
    result["pierce_weighted_dps"] = result["dps"] * numeric_column(result, "projectile_pierce")
    result["damage_per_dollar"] = result["dps"] / cost
    result["pierce_damage_per_dollar"] = result["pierce_weighted_dps"] / cost
    return result


def rows_to_frame(rows: list[sqlite3.Row]) -> pandas.DataFrame:
    if not rows:
        return pandas.DataFrame(columns=list(INPUT_COLUMNS))
    return pandas.DataFrame([dict(row) for row in rows])


def rank_upgrades(
    connection: sqlite3.Connection,
    filters: UpgradeFilters | None = None,
    metric: str = "damage_per_dollar",
    difficulty: str = "medium",
    limit: int | None = None,
) -> pandas.DataFrame:
    if metric not in METRICS:
        raise QueryError(f'Cannot rank by "{metric}". Allowed: {", ".join(METRICS)}')
    if difficulty not in DIFFICULTY_MULTIPLIERS:
        raise QueryError(f"Unknown difficulty: {difficulty!r}")
    if limit is not None and limit < 1:
        raise QueryError(f"limit must be at least 1, got {limit}")
    frame = rows_to_frame(search_upgrades(connection, filters))
    frame["total_cost"] = [
        total_cost(connection, tower, path, difficulty)
        for tower, path in zip(frame["tower_name"], frame["path"], strict=True)
    ]
    frame["total_cost"] = pandas.to_numeric(frame["total_cost"], errors="coerce")
    ranked = add_metrics(frame).sort_values(
        [metric, "total_cost", "path"], ascending=[False, True, True], na_position="last"
    )
    ranked = ranked.reset_index(drop=True)
    return ranked if limit is None else ranked.head(limit)
