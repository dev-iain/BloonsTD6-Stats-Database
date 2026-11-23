# Ranking: `total_cost`, `dps`, `damage_per_dollar`, `rank_upgrades`

## Rules for these tests

- Formulas, NULL rules, difficulty rounding and tie order are defined in `docs/ranking.md`.
- Invalid input raises `QueryError` (`btd6/query.py`).
- Floats are compared with `pytest.approx(rel=1e-6)`.
- Costs fixture: Super Monkey from `tests/fixtures/costs_super_monkey_cargo.json` (#96). Base 2500; path 1: 2000, 2500, 20000, 100000, 500000; path 2: 1500, 1900, 7500, 25000, 70000; path 3: 3000, 1200, 5600, 55555, 165650.
- Upgrade rows: Super Monkey `0-0-0`, `1-0-0`, `3-0-0`, `0-0-4` from `data.csv`, built with `tests/factories.py`, loaded into a `:memory:` database with the migrations.

| path | type | damage | count | rate | pierce | medium cost |
|---|---|---|---|---|---|---|
| `0-0-0` | Sharp | 1 | 1 | 0.045 | 1 | 2500 |
| `1-0-0` | Energy | 1 | 1 | 0.045 | 2 | 4500 |
| `3-0-0` | Plasma | 1 | 3 | 0.03 | 6 | 27000 |
| `0-0-4` | Normal | 2 | 1 | 0.0225 | 8 | 67855 |

---

## total_cost

```python
def total_cost(connection: sqlite3.Connection, tower_name: str, path: str, difficulty: str = "medium") -> int | None
```

Returns the cost of buying the tower and every tier up to `path`, at the given difficulty, or `None` if the tower's costs are not loaded.

Take the function `total_cost`. The caller wants the price of one upgrade code, so we model the shape of `path`: a single path, two paths, and every way a code can be invalid (crosspath rule, malformed, tier above 5, three paths). Each difficulty uses its own multiplier and rounding, so we model all four plus an unknown one. For the receiver state, the tower may be unknown, or known but without costs loaded.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`path`|A) Upgrade code|A1: One path, low tier|`"1-0-0"`|
|||A2: One path, tier 5|`"5-0-0"`|
|||A3: Two paths, valid crosspath|`"0-2-4"`|
|||A4: Two paths above tier 2|`"3-3-0"`|
|||A5: Malformed|`"1-0"`|
|||A6: Tier above 5|`"6-0-0"`|
|||A7: Three paths upgraded|`"1-1-1"`|
|`difficulty`|B) Difficulty|B1: Medium|`"medium"`|
|||B2: Easy|`"easy"`|
|||B3: Hard|`"hard"`|
|||B4: Impoppable|`"impoppable"`|
|||B5: Unknown|`"nightmare"`|
|`tower_name`|C) Tower|C1: Loaded|`"Super Monkey"`|
|||C2: Not in the database|`"Dart Monkey"`|
|`connection` (state: costs)|D) Costs loaded|D1: Yes|costs fixture loaded|
|||D2: No|tower row exists, `base_cost` NULL, no `upgrade_costs` rows|

Base case: A1, B1, C1, D1

### Base Choice Coverage

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | returns `4500` | `test_total_cost_all_base` |
| T2 | A2 | B1 | C1 | D1 | returns `627000` | `test_total_cost_tier_five` |
| T3 | A3 | B1 | C1 | D1 | returns `71255` | `test_total_cost_crosspath` |
| T4 | A4 | B1 | C1 | D1 | raises `QueryError` | `test_total_cost_two_paths_above_tier_two` |
| T5 | A5 | B1 | C1 | D1 | raises `QueryError` | `test_total_cost_malformed_path` |
| T6 | A6 | B1 | C1 | D1 | raises `QueryError` | `test_total_cost_tier_above_five` |
| T7 | A7 | B1 | C1 | D1 | raises `QueryError` | `test_total_cost_three_paths` |
| T8 | A1 | B2 | C1 | D1 | returns `3825` | `test_total_cost_easy` |
| T9 | A1 | B3 | C1 | D1 | returns `4860` | `test_total_cost_hard` |
| T10 | A1 | B4 | C1 | D1 | returns `5400` | `test_total_cost_impoppable` |
| T11 | A1 | B5 | C1 | D1 | raises `QueryError` | `test_total_cost_unknown_difficulty` |
| T12 | A1 | B1 | C2 | D1 | raises `QueryError` | `test_total_cost_unknown_tower` |
| T13 | A1 | B1 | C1 | D2 | returns `None` | `test_total_cost_costs_not_loaded` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T14 | base tower only (#97 round trip) | `total_cost(conn, "Super Monkey", "0-0-0")` returns `2500` | `test_total_cost_base_tower` |
| T15 | per-price rounding, hard | `total_cost(conn, "Super Monkey", "0-0-4", "hard")` returns `73285` | `test_total_cost_hard_rounds_each_price` |

---

## dps

```python
def dps(projectile_damage: float | None, projectile_count: int | None, attack_rate: float | None) -> float | None
```

Returns `projectile_damage × projectile_count / attack_rate`, or `None` when it cannot be computed.

Take the function `dps`. Each input can be missing, and `attack_rate` divides, so we model a normal value, `None` for each input, more than one projectile, and a zero rate. A missing `projectile_count` means one projectile, not "unknown".

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`projectile_damage`|A) Damage|A1: Positive|`1`|
|||A2: None|`None`|
|`projectile_count`|B) Count|B1: One|`1`|
|||B2: More than one|`3`|
|||B3: None|`None`|
|`attack_rate`|C) Seconds per attack|C1: Positive|`0.045`|
|||C2: Zero|`0`|
|||C3: None|`None`|

Base case: A1, B1, C1

### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | returns `22.2222222` | `test_dps_all_base` |
| T2 | A2 | B1 | C1 | returns `None` | `test_dps_damage_none` |
| T3 | A1 | B2 | C1 | returns `66.6666667` | `test_dps_several_projectiles` |
| T4 | A1 | B3 | C1 | returns `22.2222222` | `test_dps_count_none_means_one` |
| T5 | A1 | B1 | C2 | returns `None` | `test_dps_rate_zero` |
| T6 | A1 | B1 | C3 | returns `None` | `test_dps_rate_none` |

---

## damage_per_dollar

```python
def damage_per_dollar(metric_value: float | None, cost: int | None) -> float | None
```

Divides a damage metric by a cost, or returns `None` when either is missing or the cost is zero.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`metric_value`|A) Metric|A1: Positive|`22.2222222` (`dps(1, 1, 0.045)`)|
|||A2: None|`None`|
|`cost`|B) Cost|B1: Positive|`2500`|
|||B2: Zero|`0`|
|||B3: None|`None`|

Base case: A1, B1

### Base Choice Coverage

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | returns `0.00888889` | `test_damage_per_dollar_all_base` |
| T2 | A2 | B1 | returns `None` | `test_damage_per_dollar_metric_none` |
| T3 | A1 | B2 | returns `None` | `test_damage_per_dollar_zero_cost` |
| T4 | A1 | B3 | returns `None` | `test_damage_per_dollar_cost_none` |

---

## rank_upgrades

```python
def rank_upgrades(connection: sqlite3.Connection, filters: UpgradeFilters | None = None, metric: str = "damage_per_dollar", difficulty: str = "medium", limit: int | None = None) -> pandas.DataFrame
```

Runs `search_upgrades` with `filters`, adds `total_cost`, `dps`, `pierce_weighted_dps`, `damage_per_dollar` and `pierce_damage_per_dollar` columns, and sorts by `metric` (highest first; ties by lower cost, then path; `NULL` last).

Oracles list the `path` column in order. E2 only: add Super Monkey `0-1-0` with `attack_rate = NULL` (other stats from `0-0-0`; medium cost 4000).

Take the function `rank_upgrades`. The caller wants the best upgrades by one metric, so we model each metric plus an invalid one; the `dps` metric has a tie (`0-0-0` and `1-0-0`) that the cost tie-break must settle. Difficulty changes every cost, so we model a non-default and an invalid one. It must keep the 1.0 filters, so we model a filter. We model `limit`, a row whose metric is `NULL`, and a database without costs.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`metric`|A) Metric|A1: Damage per dollar|`"damage_per_dollar"`|
|||A2: DPS|`"dps"`|
|||A3: Pierce damage per dollar|`"pierce_damage_per_dollar"`|
|||A4: Unknown|`"bogus"`|
|`difficulty`|B) Difficulty|B1: Medium|`"medium"`|
|||B2: Hard|`"hard"`|
|||B3: Unknown|`"nightmare"`|
|`filters`|C) Filters|C1: None|`None`|
|||C2: Damage type|`UpgradeFilters(damage_type="Plasma")`|
|`limit`|D) Limit|D1: None|`None`|
|||D2: Two|`2`|
|`connection` (state: rows)|E) A `NULL` metric|E1: No|the four rows|
|||E2: Yes|plus `0-1-0` with `attack_rate = NULL`|
|`connection` (state: costs)|F) Costs loaded|F1: Yes|costs fixture loaded|
|||F2: No|no costs loaded|

Base case: A1, B1, C1, D1, E1, F1

### Base Choice Coverage

| BCC Test | A | B | C | D | E | F | Oracle | Test Name |
|---|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | F1 | paths `["0-0-0", "1-0-0", "3-0-0", "0-0-4"]`; `damage_per_dollar` of `0-0-0` is `0.00888889` | `test_rank_upgrades_all_base` |
| T2 | A2 | B1 | C1 | D1 | E1 | F1 | paths `["3-0-0", "0-0-4", "0-0-0", "1-0-0"]` (`0-0-0` and `1-0-0` tie at `22.2222`; lower cost first) | `test_rank_upgrades_dps_tie_by_cost` |
| T3 | A3 | B1 | C1 | D1 | E1 | F1 | paths `["3-0-0", "0-0-4", "1-0-0", "0-0-0"]` | `test_rank_upgrades_pierce_damage_per_dollar` |
| T4 | A4 | B1 | C1 | D1 | E1 | F1 | raises `QueryError` | `test_rank_upgrades_unknown_metric` |
| T5 | A1 | B2 | C1 | D1 | E1 | F1 | paths `["0-0-0", "1-0-0", "3-0-0", "0-0-4"]`; `total_cost` of `0-0-0` is `2700`; its `damage_per_dollar` is `0.00823045` | `test_rank_upgrades_hard` |
| T6 | A1 | B3 | C1 | D1 | E1 | F1 | raises `QueryError` | `test_rank_upgrades_unknown_difficulty` |
| T7 | A1 | B1 | C2 | D1 | E1 | F1 | paths `["3-0-0"]` | `test_rank_upgrades_keeps_filters` |
| T8 | A1 | B1 | C1 | D2 | E1 | F1 | paths `["0-0-0", "1-0-0"]` | `test_rank_upgrades_limit` |
| T9 | A1 | B1 | C1 | D1 | E2 | F1 | paths `["0-0-0", "1-0-0", "3-0-0", "0-0-4", "0-1-0"]`; `dps` of `0-1-0` is `NULL` | `test_rank_upgrades_null_metric_last` |
| T10 | A1 | B1 | C1 | D1 | E1 | F2 | paths `["0-0-0", "0-0-4", "1-0-0", "3-0-0"]`; every `total_cost` and `damage_per_dollar` is `NULL` (all tie, so path order) | `test_rank_upgrades_costs_not_loaded` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T11 | invariant (hypothesis) | for any filters and metric, the ranked paths are a permutation of `search_upgrades` paths | `test_rank_upgrades_is_permutation` |
| T12 | invariant (hypothesis) | of two upgrades with equal DPS, the more expensive one never ranks higher by `damage_per_dollar` | `test_rank_upgrades_cost_never_helps` |
