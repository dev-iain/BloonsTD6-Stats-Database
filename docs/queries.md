# Query layer contract

Proposal from the query layer (#31), written before the schema (#16). `btd6/query.py` must match this file.

## Interface

```python
@dataclass(frozen=True)
class UpgradeFilters:
    tower_name: str | None = None
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


def search_upgrades(
    connection: sqlite3.Connection,
    filters: UpgradeFilters | None = None,
    sort_by: str | None = None,
    descending: bool = True,
    limit: int | None = None,
) -> list[sqlite3.Row]: ...
```

## Filters

A filter set to `None` adds no restriction. Given filters combine with AND.

| Filter | Table.column | Rule |
|---|---|---|
| `tower_name` | `towers.name` | exact match; unknown name returns `[]` |
| `category` | `towers.category` | exact match; unknown category returns `[]` |
| `can_pop_lead` ... `can_pop_frozen` | `upgrades.can_pop_<property>` | exact match |
| `min_range` | `upgrades.range` | `>=`; `NULL` never matches |
| `min_pierce` | `upgrades.projectile_pierce` | `>=`; `NULL` never matches |
| `min_damage` | `upgrades.projectile_damage` | `>=`; `NULL` never matches |
| `min_projectile_speed` | `upgrades.projectile_speed` | `>=`; `NULL` never matches |
| `damage_type` | `damage_types.name` | exact, case-sensitive; unknown name raises `ValueError` |
| `can_hit_camo` | `upgrades.can_hit_camo` | exact match |

- `0` is a valid threshold and excludes `NULL` rows. A negative threshold raises `ValueError`.
- No filters searches every loaded tower. The CLI passes `category="Magic"` by default.

## Sorting and limit

- `sort_by` must be one of `range`, `attack_rate`, `projectile_damage`, `projectile_pierce`, `projectile_speed`, `projectile_count`, `ability_cooldown`; anything else raises `ValueError`. Build `ORDER BY` from this whitelist, never from the caller's string.
- `NULL` sorts last in both directions.
- Ties, and unsorted results, are ordered by `towers.name`, then `upgrades.path`.
- `attack_rate` is seconds between attacks (lower is faster); with `descending=True` the slowest come first.
- `limit=None` means no limit; `limit < 1` raises `ValueError`; pass the limit as a `?` parameter.

## `ValueError` messages

The CLI prints these unchanged (`tests/isp-tables/cli.md`).

| Cause | Message |
|---|---|
| negative threshold | `<field> must be 0 or more, got <value>` (e.g. `min_pierce must be 0 or more, got -1.0`) |
| unknown damage type | `Unknown damage type "<name>". Valid types: <names from damage_types, sorted, comma-separated>` |
| `sort_by` not whitelisted | `Cannot sort by "<value>". Allowed: <whitelist, comma-separated>` |
| limit below 1 | `limit must be at least 1, got <value>` |

## Result row columns

`tower_name`, `category`, `path`, `range`, `footprint_radius`, `attack_rate`, `projectile_count`, `projectile_damage`, `projectile_pierce`, `projectile_speed`, `projectile_radius`, `projectile_lifespan`, `can_hit_camo`, `ability_cooldown`, `damage_type` (name, not id), `can_pop_lead`, `can_pop_black`, `can_pop_white`, `can_pop_purple`, `can_pop_glass`, `can_pop_frozen`.

## Assumed schema (for #16)

- `towers(id, name UNIQUE, category)`
- `upgrades(tower_id -> towers.id, path, <stat columns>, damage_type_id -> damage_types.id, can_pop_* columns)`, unique on `(tower_id, path)`
- `damage_types(id, name UNIQUE)` seeded from `DAMAGE_TYPES`, plus `Unknown`
- `can_pop_*` and `can_hit_camo` stored as `INTEGER` 0/1
- indexes on the filter and sort columns

Until #16 lands, query tests build this schema in an in-memory fixture database.
