# Ranking: `total_cost`, `add_metrics`, `damage_per_dollar`, `rank_upgrades`

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

## add_metrics

```python
def add_metrics(dataframe: pandas.DataFrame) -> pandas.DataFrame
```

Replaces the first-projectile `dps` function (#134). Input columns: `upgrade_dps` and `upgrade_moab_dps` (per-attack sums from `all_upgrade_dps`, `docs/schema.md` "DPS definitions"; `NULL` when no attack contributes), `projectile_pierce` and `total_cost`. Adds `dps` (= `upgrade_dps`), `moab_dps` (= `upgrade_moab_dps`), `pierce_weighted_dps`, `damage_per_dollar`, `pierce_damage_per_dollar`; the input is not mutated and row order is kept. `projectile_damage`, `projectile_count` and `attack_rate` are no longer read: the per-attack math lives in `upgrade_dps` (`attacks.md`, T1-T11).

Take the function `add_metrics`. The DPS sums can be missing, the pierce can be missing (including the `9999999` sentinel stored as `NULL`), and the cost can be missing or zero, so we model each as a normal value, `None`, and for the cost a zero. Non-numeric input coerces to `NaN`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`upgrade_dps`|A) DPS sum|A1: Positive|`22.2222222`|
|||A2: None|`None`|
|||A3: Not a number|`"abc"`|
|`upgrade_moab_dps`|B) MOAB DPS sum|B1: Positive|`30.0`|
|||B2: None|`None`|
|`projectile_pierce`|C) Pierce|C1: Positive|`2.0`|
|||C2: None (also the unlimited sentinel)|`None`|
|`total_cost`|D) Cost|D1: Positive|`4500.0`|
|||D2: Zero|`0.0`|
|||D3: None|`None`|

Base case: A1, B1, C1, D1

### Base Choice Coverage

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | `dps` 22.2222222, `moab_dps` 30, `pierce_weighted_dps` 44.4444444, `damage_per_dollar` 0.00493827, `pierce_damage_per_dollar` 0.00987654 | `test_add_metrics_all_base` |
| T2 | A2 | B1 | C1 | D1 | `dps`, `pierce_weighted_dps`, `damage_per_dollar` `NaN`; `moab_dps` 30 | `test_add_metrics_null_and_zero_inputs` |
| T3 | A3 | B1 | C1 | D1 | `dps`, `pierce_weighted_dps`, `damage_per_dollar` `NaN` | `test_add_metrics_non_numeric_dps_is_nan` |
| T4 | A1 | B2 | C1 | D1 | `moab_dps` `NaN`; the rest set | `test_add_metrics_null_and_zero_inputs` |
| T5 | A1 | B1 | C2 | D1 | `pierce_weighted_dps` `NaN`; `dps`, `damage_per_dollar` set | `test_add_metrics_null_and_zero_inputs` |
| T6 | A1 | B1 | C1 | D2 | `damage_per_dollar` `NaN`; `dps` set | `test_add_metrics_null_and_zero_inputs` |
| T7 | A1 | B1 | C1 | D3 | `damage_per_dollar` `NaN`; `dps` set | `test_add_metrics_null_and_zero_inputs` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T8 | old columns ignored | `projectile_damage`, `projectile_count`, `attack_rate` in the input do not change `dps` | `test_add_metrics_ignores_first_projectile_columns` |
| T9 | input not mutated | no `dps` or `moab_dps` column added to the input | `test_add_metrics_does_not_mutate_input` |
| T10 | row order | `dps` keeps input order | `test_add_metrics_keeps_row_order` |

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

Runs `search_upgrades` with `filters`, adds `total_cost`, `dps` (per-attack sum), `moab_dps`, `pierce_weighted_dps`, `damage_per_dollar` and `pierce_damage_per_dollar` columns, and sorts by `metric` (highest first; ties by lower cost, then path; `NULL` last).

Oracles list the `path` column in order. E2 only: add Super Monkey `0-1-0` with `attack_rate = NULL` (other stats from `0-0-0`; medium cost 4000).

Take the function `rank_upgrades`. The caller wants the best upgrades by one metric, so we model each metric plus an invalid one; the `dps` metric has a tie (`0-0-0` and `1-0-0`) that the cost tie-break must settle. Difficulty changes every cost, so we model a non-default and an invalid one. It must keep the 1.0 filters, so we model a filter. We model `limit`, a row whose metric is `NULL`, and a database without costs.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`metric`|A) Metric|A1: Damage per dollar|`"damage_per_dollar"`|
|||A2: DPS|`"dps"`|
|||A3: Pierce damage per dollar|`"pierce_damage_per_dollar"`|
|||A5: MOAB DPS|`"moab_dps"`|
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

---

## Per-attack data (#134)

Fixtures: `tests/factories.py` (`ninja_003`, `wizard_005`, `wizard_400`, `druid_030`, `druid_400`, `druid_040`, `alchemist_220`, `alchemist_040`) loaded with `load_tower`. Those towers have no costs, so per-dollar metrics are `NULL`; the checks use `dps` and `moab_dps`. Files: `tests/test_upgrade_dps.py` (`upgrade_dps`, `upgrade_moab_dps`, `all_upgrade_dps`; ISP in `attacks.md`) and `tests/test_ranking_attacks.py`.

| Upgrade | `dps` | `moab_dps` | Test |
|---|---|---|---|
| Ninja 0-0-3 | 6.70802 (Explosion counted; first projectile alone gives `NULL`) | 6.70802 | `test_rank_upgrades_uses_per_attack_sum`, `test_ninja_003_dps_uses_explosion_projectile` |
| Wizard 4-0-0 | 21.81818 | 58.18182 | `test_rank_upgrades_uses_per_attack_sum` |
| Druid 0-3-0 | 7.65734 | 7.65734 | same; `Collidable` sentinel excluded |
| Druid 4-0-0 | 6.34980 | 6.34980 | same; `Spawning projectile` pierce sentinel unused |
| Alchemist 2-2-0 | `NULL` | `NULL` | `test_rank_upgrades_alchemist_220_null_dps_ranks_last` (ranks last on every metric) |
| Wizard 0-0-5, without the `MOAB` attack | `1/0.275 + 2/1.5 = 4.9697` | | `test_wizard_005_stable_part_without_moab_attack`, `test_rank_upgrades_wizard_005_stable_lower_bound` |
| Wizard 0-0-5 | 18.30303 | 38.30303 | `test_wizard_005_moab_and_bfb_are_alternatives`, `test_rank_upgrades_wizard_005_moab_and_bfb_are_alternatives`: `MOAB` (40) and `BFB` (100) are per-summon alternatives; DPS takes the smallest (`1/0.275 + 2/1.5 + 40/3`), MOAB DPS the largest (`... + 100/3`) |

Sentinel: no ranking column is infinite for Druid; a first projectile with unlimited pierce gives `NULL` `pierce_weighted_dps`. Cooldown: `search_upgrades(sort_by="ability_cooldown")` treats `0` like `NULL` (`NULLIF(ability_cooldown, 0)`): Alchemist 0-4-0 (60), then Alchemist 2-2-0 (`NULL`), Druid 0-4-0 (0), in both directions (`test_ability_cooldown_zero_sorts_like_no_ability`). Invariant (hypothesis): `dps` is `None` or finite and `moab_dps >= dps` (`test_dps_is_finite_and_moab_dps_never_lower`).
