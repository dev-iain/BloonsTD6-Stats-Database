from __future__ import annotations

import sqlite3

import pandas

from btd6.costs import total_cost, validate_difficulty
from btd6.query import QueryError, UpgradeFilters, search_upgrades

METRICS = ("dps", "moab_dps", "damage_per_dollar", "pierce_damage_per_dollar")
INPUT_COLUMNS = (
    "tower_name",
    "path",
    "projectile_pierce",
    "upgrade_dps",
    "upgrade_moab_dps",
)
BLOON_CLASS_NAMES = frozenset({"MOAB", "BFB", "ZOMG", "DDT", "BAD"})
DPS_SQL = """
SELECT upgrades.id AS upgrade_id, attacks.id AS attack_id, attacks.rate AS rate,
    projectiles.name AS name, projectiles.damage AS damage,
    projectiles.unlimited_damage AS unlimited_damage,
    projectiles.moab_bonus_damage AS moab_bonus_damage,
    projectiles.moab_only AS moab_only, projectiles.count AS count
FROM upgrades
LEFT JOIN attacks ON attacks.upgrade_id = upgrades.id
LEFT JOIN projectiles ON projectiles.attack_id = attacks.id
"""
DPS_ORDER_SQL = " ORDER BY upgrades.id, attacks.attack_index, projectiles.projectile_index"
Figures = tuple[float | None, float | None]


def numeric_column(frame: pandas.DataFrame, name: str) -> pandas.Series:
    return pandas.to_numeric(frame[name], errors="coerce").astype(float)


def add_metrics(dataframe: pandas.DataFrame) -> pandas.DataFrame:
    result = dataframe.copy()
    cost = numeric_column(result, "total_cost").where(lambda series: series != 0)
    result["dps"] = numeric_column(result, "upgrade_dps")
    result["moab_dps"] = numeric_column(result, "upgrade_moab_dps")
    result["pierce_weighted_dps"] = result["dps"] * numeric_column(result, "projectile_pierce")
    result["damage_per_dollar"] = result["dps"] / cost
    result["pierce_damage_per_dollar"] = result["pierce_weighted_dps"] / cost
    return result


def projectile_hits(row: sqlite3.Row) -> Figures:
    if row["damage"] is None or row["unlimited_damage"]:
        return None, None
    count = 1 if row["count"] is None else row["count"]
    moab_hit = (row["damage"] + (row["moab_bonus_damage"] or 0)) * count
    plain_hit = None if row["moab_only"] else row["damage"] * count
    return plain_hit, moab_hit


def sum_or_none(values: list[float]) -> float | None:
    return sum(values) if values else None


def attack_totals(projectiles: list[sqlite3.Row]) -> Figures:
    fixed: tuple[list[float], list[float]] = ([], [])
    alternatives: tuple[list[float], list[float]] = ([], [])
    for row in projectiles:
        hits = projectile_hits(row)
        target = alternatives if row["name"] in BLOON_CLASS_NAMES else fixed
        for damage_hit, bucket in zip(hits, target, strict=True):
            if damage_hit is not None:
                bucket.append(damage_hit)
    plain = fixed[0] + ([min(alternatives[0])] if alternatives[0] else [])
    moab = fixed[1] + ([max(alternatives[1])] if alternatives[1] else [])
    return sum_or_none(plain), sum_or_none(moab)


def add_optional(total: float | None, part: float | None) -> float | None:
    if part is None:
        return total
    return part if total is None else total + part


def combine_attacks(attacks: dict[int, list[sqlite3.Row]]) -> Figures:
    plain_total: float | None = None
    moab_total: float | None = None
    for projectiles in attacks.values():
        rate = projectiles[0]["rate"]
        if not rate:
            continue
        plain, moab = attack_totals([row for row in projectiles if row["name"] is not None])
        plain_total = add_optional(plain_total, None if plain is None else plain / rate)
        moab_total = add_optional(moab_total, None if moab is None else moab / rate)
    return plain_total, moab_total


def dps_by_upgrade(
    connection: sqlite3.Connection, upgrade_id: int | None = None
) -> dict[int, Figures]:
    where = "" if upgrade_id is None else " WHERE upgrades.id = ?"
    params = [] if upgrade_id is None else [upgrade_id]
    grouped: dict[int, dict[int, list[sqlite3.Row]]] = {}
    for row in connection.execute(DPS_SQL + where + DPS_ORDER_SQL, params):
        attacks = grouped.setdefault(row["upgrade_id"], {})
        if row["attack_id"] is not None:
            attacks.setdefault(row["attack_id"], []).append(row)
    return {key: combine_attacks(attacks) for key, attacks in grouped.items()}


def all_upgrade_dps(connection: sqlite3.Connection) -> dict[int, Figures]:
    return dps_by_upgrade(connection)


def upgrade_dps(connection: sqlite3.Connection, upgrade_id: int) -> float | None:
    return dps_by_upgrade(connection, upgrade_id).get(upgrade_id, (None, None))[0]


def upgrade_moab_dps(connection: sqlite3.Connection, upgrade_id: int) -> float | None:
    return dps_by_upgrade(connection, upgrade_id).get(upgrade_id, (None, None))[1]


def rows_to_frame(rows: list[sqlite3.Row]) -> pandas.DataFrame:
    if not rows:
        return pandas.DataFrame(columns=list(INPUT_COLUMNS))
    return pandas.DataFrame([dict(row) for row in rows])


def attach_dps(connection: sqlite3.Connection, frame: pandas.DataFrame) -> None:
    upgrade_ids_by_key = {
        (row["name"], row["path"]): row["id"]
        for row in connection.execute(
            "SELECT towers.name AS name, upgrades.path AS path, upgrades.id AS id"
            " FROM upgrades JOIN towers ON towers.id = upgrades.tower_id"
        )
    }
    figures = all_upgrade_dps(connection)
    keys = [upgrade_ids_by_key[key] for key in zip(frame["tower_name"], frame["path"], strict=True)]
    frame["upgrade_dps"] = [figures[key][0] for key in keys]
    frame["upgrade_moab_dps"] = [figures[key][1] for key in keys]


def rank_upgrades(
    connection: sqlite3.Connection,
    filters: UpgradeFilters | None = None,
    metric: str = "damage_per_dollar",
    difficulty: str = "medium",
    limit: int | None = None,
) -> pandas.DataFrame:
    if metric not in METRICS:
        raise QueryError(f'Cannot rank by "{metric}". Allowed: {", ".join(METRICS)}')
    validate_difficulty(difficulty)
    if limit is not None and limit < 1:
        raise QueryError(f"limit must be at least 1, got {limit}")
    frame = rows_to_frame(search_upgrades(connection, filters))
    attach_dps(connection, frame)
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
