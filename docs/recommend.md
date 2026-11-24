# Recommender: round-fit score and affordability

`btd6/recommend.py`: `recommend(connection, round_number, money, difficulty="medium", limit=None) -> list[Recommendation]` (epic #119). It returns the upgrades you can afford that can pop everything the round contains, ranked by how well they fit the round. The rules are deterministic: no randomness, no LLM. Tests: `tests/isp-tables/recommend.md`.

Inputs come from two existing modules:

- `round_threats` (`btd6/threats.py`, `docs/threats.md`): `camo_share`, `property_share[prop]`, `moab_share`.
- `rank_upgrades` (`btd6/ranking.py`, `docs/ranking.md`): `total_cost`, `dps`, `moab_dps`, `pierce_weighted_dps`, `projectile_pierce`, `can_hit_camo`, `can_pop_*`.

## Constants

| Name | Value | Reason |
|---|---|---|
| `MIN_PROPERTY_SHARE` | `0.05` | A property that makes up less than 5% of the round's RBE can be handled by a second tower, so it should not remove every other upgrade from the list. Round 63's lead share (0.1197) is above the threshold. |
| `HIGH_PIERCE` | `5` | Smallest `projectile_pierce` labelled `high_pierce`. Base Dart Monkey has pierce 2 and base Super Monkey 1, while crowd-clearing tiers start around 5 (Super Monkey `3-0-0` has 6). |

## Eligibility

An upgrade is a candidate only if all of these hold:

1. `total_cost` is not NULL and `total_cost <= money`. A NULL cost (costs not loaded) is never affordable.
2. If `camo_share > 0`: `can_hit_camo` is true. Any camo at all is a leak, so camo is a hard filter.
3. For every property with `property_share[prop] >= MIN_PROPERTY_SHARE`: `can_pop_<prop>` is true.

Rules 2 and 3 go into an `UpgradeFilters` (`filters_for_threats`), so the filtering happens in SQL through `search_upgrades`. Rule 1 is applied to the `rank_upgrades` frame.

## Score

With `m = moab_share`:

```
moab_term   = m × moab_dps
pierce_term = (1 − m) × pierce_weighted_dps
score       = (moab_term + pierce_term) / total_cost
```

- MOABs have one hit target and many layers, so they need single-target damage (`moab_dps`, which includes MOAB bonus damage and `moab_only` projectiles). Everything else comes in crowds, so pierce counts (`pierce_weighted_dps = dps × projectile_pierce`).
- The epic's draft used `dps` for the MOAB term. `moab_dps` is used here instead because epic #131 (MOAB bonus damage per attack) has landed. For an upgrade without MOAB bonus damage the two are equal.
- Dividing by `total_cost` makes it "fit per dollar", like `damage_per_dollar`.

### NULL handling

- A term whose weight is `0` is left out. If `m = 0`, a NULL `moab_dps` does not matter. If `m = 1`, a NULL `projectile_pierce` does not matter.
- If a term with a non-zero weight is NULL, the score is NULL.
- `total_cost` of `0` gives a NULL score. NULL costs are already filtered out by eligibility.
- NULL scores rank last. They are still returned, because the upgrade is affordable and can pop the round.

## Ordering

Highest score first. Ties go to the lower `total_cost`, then `tower_name`, then `path` (the same order as `rank_upgrades`, with `tower_name` added because the candidates span towers). `limit` is applied after sorting.

## `Recommendation`

Frozen dataclass:

| Field | Type | Source |
|---|---|---|
| `tower_name` | `str` | `search_upgrades` |
| `path` | `str` | `X-Y-Z` |
| `total_cost` | `int` | `total_cost` at `difficulty` |
| `score` | `float \| None` | formula above |
| `dps` | `float \| None` | `add_metrics` |
| `moab_dps` | `float \| None` | `add_metrics` |
| `pierce_weighted_dps` | `float \| None` | `add_metrics` |
| `projectile_pierce` | `float \| None` | `search_upgrades` |
| `reasons` | `tuple[str, ...]` | reason codes, in the order listed below |

### Reason codes

| Code | When |
|---|---|
| `affordable` | always (every result passed rule 1) |
| `hits_camo` | the round has camo (`camo_share > 0`) |
| `pops_<prop>` | for each property required by rule 3, in `PROPERTY_NAMES` order (`pops_lead`, `pops_black`, …) |
| `high_pierce` | `pierce_term > moab_term` and `projectile_pierce >= HIGH_PIERCE` |
| `high_single_target` | `moab_term > pierce_term` |

A NULL term counts as `0` when the terms are compared. At most one of `high_pierce` and `high_single_target` is given.

## Errors

| Input | Error | Message |
|---|---|---|
| `money` not an `int`, or a `bool` | `QueryError` | `money must be a whole number, got '5000'` (`{money!r}`) |
| `money < 0` | `QueryError` | `money must be 0 or more, got -1` |
| `difficulty` not easy/medium/hard/impoppable | `QueryError` | from `validate_difficulty` |
| `limit` not an `int` (or a `bool`) | `QueryError` | `limit must be a whole number, got '3'` |
| `limit < 1` | `QueryError` | `limit must be at least 1, got 0` (same as `rank_upgrades`) |
| `round_number` not an `int`, or outside the loaded rounds | `QueryError` | the `validate_round` message, e.g. `Round 150 is not loaded; loaded rounds are 1-100` |
| no rounds loaded | `NoRoundDataError` | `No round data loaded` |

Validation order: `money`, `difficulty`, `limit`, then the round.

`money = 0`, or costs not loaded, gives `[]`. These are not errors.

## Worked examples (Super Monkey, medium, data from `docs/ranking.md`)

| Upgrade | Type | pops lead | camo | DPS = MOAB DPS | pierce | pierce DPS | cost |
|---|---|---|---|---|---|---|---|
| `0-0-0` | Sharp | no | no | 22.2222 | 1 | 22.2222 | 2500 |
| `1-0-0` | Energy | no | no | 22.2222 | 2 | 44.4444 | 4500 |
| `3-0-0` | Plasma | yes | no | 100 | 6 | 600 | 27000 |
| `0-0-4` | Normal | yes | yes | 88.8889 | 8 | 711.111 | 67855 |

Real round data (wiki, 2026-11-23) with `money = 100000`:

**Round 40** (`moab_share` 1.0, no properties, no camo). All four are eligible. `score = moab_dps / cost`:

| Rank | Upgrade | score | reasons |
|---|---|---|---|
| 1 | `0-0-0` | 0.00888889 | `affordable`, `high_single_target` |
| 2 | `1-0-0` | 0.00493827 | `affordable`, `high_single_target` |
| 3 | `3-0-0` | 0.00370370 | `affordable`, `high_single_target` |
| 4 | `0-0-4` | 0.00130998 | `affordable`, `high_single_target` |

**Round 63** (`moab_share` 0, lead 0.1197 ≥ 0.05, no camo). Only lead poppers are eligible. `score = pierce DPS / cost`:

| Rank | Upgrade | score | reasons |
|---|---|---|---|
| 1 | `3-0-0` | 0.0222222 | `affordable`, `pops_lead`, `high_pierce` |
| 2 | `0-0-4` | 0.0104799 | `affordable`, `pops_lead`, `high_pierce` |

**Round 1** (20 Red, `moab_share` 0, nothing required). This isolates the pierce effect:

| Rank | Upgrade | score | reasons |
|---|---|---|---|
| 1 | `3-0-0` | 0.0222222 | `affordable`, `high_pierce` |
| 2 | `0-0-4` | 0.0104799 | `affordable`, `high_pierce` |
| 3 | `1-0-0` | 0.00987654 | `affordable` |
| 4 | `0-0-0` | 0.00888889 | `affordable` |

Pierce against single-target: `1-0-0` (pierce 2) ranks above `0-0-0` (pierce 1) in round 1, and below it in round 40. The two have the same DPS. Round 63's top pick (`3-0-0`, pierce 6) ranks third in round 40.

On the full database with `money = 5000`, round 63's top picks are Boomerang Monkey `4-0-2` and Dart Monkey `4-2-0` (pierce 60). Round 40's top pick is Bomb Shooter `0-3-2` (MOAB DPS 48.5, pierce 1).

## Limitations

- Round 63 has no camo in the wiki's `DefaultRoundSet` (`docs/threats.md`), so its results are not required to hit camo, even though the roadmap mentions camo.
- Ceramic adds no property. Its weight comes in through the RBE-weighted pierce term, not through a filter.
- Stats are per upgrade. The recommender does not consider towers you already own (#138), buffs, abilities, or placement.
