# Query layer contract (proposal)

Status: **proposal** from the query layer (#31), written before the schema (#16) exists.
This lists what `btd6/query.py` needs from the database. If the final schema differs,
the query layer will adapt through one small mapping, so nothing here blocks #16.

## Public interface

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

The `can_pop` filter is one field per bloon property rather than a mapping, so the frozen
dataclass stays hashable and each field matches one column name.

## Filters

Every filter left as `None` adds no restriction. Filters that are given combine with AND.

| Filter | Table.column it reads | Rule |
|---|---|---|
| `tower_name` | `towers.name` | exact match; unknown name returns `[]` |
| `category` | `towers.category` | exact match; unknown category returns `[]` |
| `can_pop_lead` ... `can_pop_frozen` | `upgrades.can_pop_<property>` | `True` / `False` exact match |
| `min_range` | `upgrades.range` | `>=`; `NULL` never matches |
| `min_pierce` | `upgrades.projectile_pierce` | `>=`; `NULL` never matches |
| `min_damage` | `upgrades.projectile_damage` | `>=`; `NULL` never matches |
| `min_projectile_speed` | `upgrades.projectile_speed` | `>=`; `NULL` never matches |
| `damage_type` | `damage_types.name` | exact, case-sensitive; unknown name raises `ValueError` listing valid names |
| `can_hit_camo` | `upgrades.can_hit_camo` | `True` / `False` exact match |

Decisions:
- A negative numeric threshold raises `ValueError`. `0` is valid and excludes `NULL` rows.
- `search_upgrades` with no filters searches every loaded tower. The CLI passes
  `category="Magic"` by default, so the 1.0 "magic monkeys only" scope is a CLI default,
  not hardcoded in the query layer.

## Sorting and limit

- `sort_by` must be one of: `range`, `attack_rate`, `projectile_damage`, `projectile_pierce`,
  `projectile_speed`, `projectile_count`, `ability_cooldown`. Anything else raises `ValueError`
  listing the allowed values. The column name is taken from this whitelist, never from the
  caller's string.
- `NULL` values sort last in both directions.
- `attack_rate` is seconds between attacks, so lower is faster. With the default
  `descending=True` it lists the slowest upgrades first; the CLI should sort it ascending
  when the user asks for the fastest.
- Ties, and unsorted results, are ordered by `towers.name`, then `upgrades.path`, so output is
  always deterministic.
- `limit=None` means no limit; `limit < 1` raises `ValueError`; the value is passed as a `?`
  parameter.

## Result row columns

`tower_name`, `category`, `path`, `range`, `footprint_radius`, `attack_rate`,
`projectile_count`, `projectile_damage`, `projectile_pierce`, `projectile_speed`,
`projectile_radius`, `projectile_lifespan`, `can_hit_camo`, `ability_cooldown`, `damage_type`
(the name, not the id), `can_pop_lead`, `can_pop_black`, `can_pop_white`, `can_pop_purple`,
`can_pop_glass`, `can_pop_frozen`.

These are the `extract_row` columns plus `tower_name` and `category`.

## What this assumes about the schema (for #16)

- `towers(id, name UNIQUE, category)`
- `upgrades(tower_id -> towers.id, path, <stat columns>, damage_type_id -> damage_types.id,
  can_pop_* columns)`, unique on `(tower_id, path)`
- `damage_types(id, name UNIQUE)` seeded from `DAMAGE_TYPES`, plus `Unknown`
- `can_pop_*` and `can_hit_camo` stored as `INTEGER` 0/1
- Indexes on the filter and sort columns above

If `can_pop_*` ends up derived through a join on `damage_types` instead of stored on
`upgrades`, only the SQL builder changes; the interface above stays the same.

Until #16 lands, query tests run against an in-memory fixture database built with the
schema above (`tests/fixtures/`).
