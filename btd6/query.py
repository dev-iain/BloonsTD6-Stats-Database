from __future__ import annotations

import sqlite3
from dataclasses import dataclass

SORT_COLUMNS = (
    "range",
    "attack_rate",
    "projectile_damage",
    "projectile_pierce",
    "projectile_speed",
    "projectile_count",
    "ability_cooldown",
    "path",
)

POP_PROPERTIES = ("lead", "black", "white", "purple", "glass", "frozen")

EXACT_COLUMNS = {
    "tower_name": "towers.name",
    "category": "towers.category",
    "can_hit_camo": "upgrades.can_hit_camo",
    **{f"can_pop_{name}": f"damage_types.can_pop_{name}" for name in POP_PROPERTIES},
}

THRESHOLD_COLUMNS = {
    "min_range": "upgrades.range",
    "min_pierce": "upgrades.projectile_pierce",
    "min_damage": "upgrades.projectile_damage",
    "min_projectile_speed": "upgrades.projectile_speed",
}

SELECT_SQL = """
SELECT towers.name AS tower_name, towers.category AS category, upgrades.path AS path,
    upgrades.range AS range, upgrades.footprint_radius AS footprint_radius,
    upgrades.attack_rate AS attack_rate, upgrades.projectile_count AS projectile_count,
    upgrades.projectile_damage AS projectile_damage,
    upgrades.projectile_pierce AS projectile_pierce,
    upgrades.projectile_speed AS projectile_speed,
    upgrades.projectile_radius AS projectile_radius,
    upgrades.projectile_lifespan AS projectile_lifespan,
    upgrades.can_hit_camo AS can_hit_camo, upgrades.ability_cooldown AS ability_cooldown,
    damage_types.name AS damage_type,
    damage_types.can_pop_lead AS can_pop_lead, damage_types.can_pop_black AS can_pop_black,
    damage_types.can_pop_white AS can_pop_white,
    damage_types.can_pop_purple AS can_pop_purple,
    damage_types.can_pop_glass AS can_pop_glass,
    damage_types.can_pop_frozen AS can_pop_frozen
FROM upgrades
JOIN towers ON towers.id = upgrades.tower_id
JOIN damage_types ON damage_types.id = upgrades.damage_type_id
"""


class QueryError(ValueError):
    """Invalid search input."""


@dataclass(frozen=True)
class UpgradeFilters:
    tower_name: str | None = None
    tower_name_contains: str | None = None
    category: str | None = None
    can_pop_lead: bool | None = None
    can_pop_black: bool | None = None
    can_pop_white: bool | None = None
    can_pop_purple: bool | None = None
    can_pop_glass: bool | None = None
    can_pop_frozen: bool | None = None
    min_range: float | None = None
    min_pierce: float | None = None
    min_damage: float | None = None
    min_projectile_speed: float | None = None
    damage_type: str | None = None
    can_hit_camo: bool | None = None


def exact_clause(column: str, value: object) -> tuple[str, list[object]]:
    if isinstance(value, bool):
        value = int(value)
    return f"{column} = ?", [value]


def threshold_clause(field: str, column: str, value: float) -> tuple[str, list[object]]:
    if value < 0:
        raise QueryError(f"{field} must be 0 or more, got {value}")
    return f"{column} >= ?", [value]


def damage_type_clause(connection: sqlite3.Connection, name: str) -> tuple[str, list[object]]:
    rows = connection.execute("SELECT name FROM damage_types ORDER BY name").fetchall()
    valid = [row[0] for row in rows]
    if name not in valid:
        raise QueryError(f'Unknown damage type "{name}". Valid types: {", ".join(valid)}')
    return "damage_types.name = ?", [name]


def name_contains_clause(value: str) -> tuple[str, list[object]]:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "towers.name LIKE ? ESCAPE '\\'", [f"%{escaped}%"]


def build_where(
    connection: sqlite3.Connection, filters: UpgradeFilters
) -> tuple[str, list[object]]:
    clauses: list[tuple[str, list[object]]] = []
    for field, column in EXACT_COLUMNS.items():
        value = getattr(filters, field)
        if value is not None:
            clauses.append(exact_clause(column, value))
    for field, column in THRESHOLD_COLUMNS.items():
        value = getattr(filters, field)
        if value is not None:
            clauses.append(threshold_clause(field, column, value))
    name_part = (filters.tower_name_contains or "").strip()
    if name_part:
        clauses.append(name_contains_clause(name_part))
    if filters.damage_type is not None:
        clauses.append(damage_type_clause(connection, filters.damage_type))
    if not clauses:
        return "", []
    sql = " WHERE " + " AND ".join(clause for clause, _ in clauses)
    return sql, [param for _, params in clauses for param in params]


def build_order_by(sort_by: str | None, descending: bool) -> str:
    tiebreak = "towers.name, upgrades.path"
    if sort_by is None:
        return f" ORDER BY {tiebreak}"
    if sort_by not in SORT_COLUMNS:
        allowed = ", ".join(SORT_COLUMNS)
        raise QueryError(f'Cannot sort by "{sort_by}". Allowed: {allowed}')
    direction = "DESC" if descending else "ASC"
    return f" ORDER BY upgrades.{sort_by} {direction} NULLS LAST, {tiebreak}"


def search_upgrades(
    connection: sqlite3.Connection,
    filters: UpgradeFilters | None = None,
    sort_by: str | None = None,
    descending: bool = True,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    if filters is None:
        filters = UpgradeFilters()
    where_sql, params = build_where(connection, filters)
    order_sql = build_order_by(sort_by, descending)
    limit_sql = ""
    if limit is not None:
        if limit < 1:
            raise QueryError(f"limit must be at least 1, got {limit}")
        limit_sql = " LIMIT ?"
        params.append(limit)
    return connection.execute(SELECT_SQL + where_sql + order_sql + limit_sql, params).fetchall()
