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
| `tower_name_contains` | `towers.name` | stripped; `None`/empty/whitespace adds no filter; case-insensitive substring via `LIKE ? ESCAPE '\'` with `\`, `%`, `_` escaped so they match literally; `tower_name` stays exact |
| `category` | `towers.category` | exact match; unknown category returns `[]` |
| `can_pop_lead` ... `can_pop_frozen` | `damage_types.can_pop_<property>` | exact match; `NULL` (the `Unknown` damage type) never matches, for `True` or `False` |
| `min_range` | `upgrades.range` | `>=`; `NULL` never matches |
| `min_pierce` | `upgrades.projectile_pierce` | `>=`; `NULL` never matches |
| `min_damage` | `upgrades.projectile_damage` | `>=`; `NULL` never matches |
| `min_projectile_speed` | `upgrades.projectile_speed` | `>=`; `NULL` never matches |
| `damage_type` | `damage_types.name` | exact, case-sensitive; unknown name raises `ValueError` |
| `can_hit_camo` | `upgrades.can_hit_camo` | exact match |

- `0` is a valid threshold and excludes `NULL` rows. A negative threshold raises `ValueError`.
- No filters searches every loaded tower. The CLI passes `category="Magic"` by default.

## Sorting and limit

- `sort_by` must be one of `range`, `attack_rate`, `projectile_damage`, `projectile_pierce`, `projectile_speed`, `projectile_count`, `ability_cooldown`, `path`; anything else raises `ValueError`. Build `ORDER BY` from this whitelist, never from the caller's string.
- `NULL` sorts last in both directions.
- Ties, and unsorted results, are ordered by `towers.name`, then `upgrades.path`.
- `attack_rate` is seconds between attacks (lower is faster); with `descending=True` the slowest come first.
- `limit=None` means no limit; `limit < 1` raises `ValueError`; pass the limit as a `?` parameter.

## `ValueError` messages

These are raised as `QueryError`, a subclass of `ValueError` defined in `btd6/query.py`. The CLI catches `QueryError` only, prints the message unchanged and exits with `2` (`tests/isp-tables/cli.md`); any other exception is an unexpected error.

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
- `upgrades(tower_id -> towers.id, path, <stat columns>, can_hit_camo, damage_type_id -> damage_types.id)`, unique on `(tower_id, path)`
- `damage_types(id, name UNIQUE, can_pop_lead, can_pop_black, can_pop_white, can_pop_purple, can_pop_glass, can_pop_frozen)` seeded from `DAMAGE_TYPES`, plus `Unknown`
- `can_hit_camo` and `can_pop_*` stored as `INTEGER` 0/1; `can_pop_*` is `NULL` for `Unknown`
- indexes on the filter and sort columns
- `cost` is not part of the 1.0 schema; it arrives in 2.0 as a nullable `upgrades.cost` column added by migration

### Decision: `can_pop_*` live on `damage_types`

Every `can_pop_*` value is a function of the damage type, so storing it per upgrade would be a transitive dependency (not 3NF) and could drift from `damage_type_id`. The flags are therefore seeded once in `damage_types`, and `search_upgrades` reads them through the `damage_types` join it already needs for `damage_type`. `extract_row` still returns the flags, but the loader uses only the damage type name to look up `damage_type_id`. `Unknown` is seeded with `NULL` flags, because an unmapped bitmask says nothing about what can be popped. The result row columns are unchanged.

Until #16 lands, query tests build this schema in an in-memory fixture database.

## Round queries (`btd6/rounds.py`, #87)

```python
@dataclass(frozen=True)
class RoundGroup:
    group_index: int
    bloon: str
    is_camo: bool
    is_regrow: bool
    is_fortified: bool
    count: int
    start: float
    duration: float
    rbe: int | None
    is_moab: bool


@dataclass(frozen=True)
class RoundSummary:
    round: int
    total_bloons: int
    total_rbe: int
    has_moab: bool
    has_camo: bool
    has_lead: bool
    has_ceramic: bool


def get_round(connection: sqlite3.Connection, round_number: int) -> list[RoundGroup]: ...
def get_round_summary(connection: sqlite3.Connection, round_number: int) -> RoundSummary: ...
```

- `get_round` returns the groups of one round ordered by `group_index`; repeated bloons are not merged. `bloon` is the base name (`Blue` with `is_camo` for a camo Blue); `rbe` and `is_moab` come from the base bloon.
- `get_round_summary` aggregates the groups: `total_bloons` is the sum of `count`; `total_rbe` is the sum of `count * rbe` using the base bloon's `rbe` (fortified health is not applied); `has_lead` and `has_ceramic` follow the base bloon name (a camo Lead sets `has_lead` and `has_camo`).
- Argument validation is shared. SQL is parameterized.

| Cause | Error |
|---|---|
| `round_number` not an `int` (including `bool`, `float`, `str`, `None`) | `TypeError` |
| round below 1 or above the highest loaded round | `ValueError`: `Round <n> is not loaded; loaded rounds are 1-<max>` |
| no rows in `rounds` | `ValueError` (`NoRoundDataError`): `No round data loaded` |

CLI: `python -m btd6 rounds --round N` or `--from A --to B` (inclusive) prints columns `round, bloon, count, camo, regrow, fortified, start, duration, rbe`. A missing database or empty round tables exits `1`; a `ValueError` (including `--from` greater than `--to`) prints one stderr line and exits `2`. Argparse errors exit `2`.
