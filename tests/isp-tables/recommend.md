# Recommender: `recommend`, `filters_for_threats`, `effective_pierce`, `unmet_needs`, `round_score`, `reasons_for`, `sort_key`

## Rules for these tests

- Rules, constants, NULL handling and tie order are defined in `docs/recommend.md`.
- **Signatures chosen for the helpers** (the doc names only some): `effective_pierce(pierce, range, density) -> float | None`; `unmet_needs(row: Mapping, threats: RoundThreats) -> tuple[str, ...]` (`row` is a `rank_upgrades` record with `can_hit_camo` and `can_pop_<prop>`); `round_score(moab_share, moab_dps, dps, effective_pierce, total_cost) -> float | None`; `reasons_for(threats, moab_dps, dps, effective_pierce) -> tuple[str, ...]` (current-round codes only, no `fails_*`); `sort_key(item)`; `recommend(connection, round_number, money, difficulty="medium", limit=None, horizon=DEFAULT_HORIZON)`. `Recommendation` gains `effective_pierce` and `first_leak_round` before `reasons`.
- Window oracle: tests recompute the decay-weighted mean from the fixture files (`tests/recommend_fixture.py`: `round_density`, `plain_window_score`), independent of `btd6/`. The four-upgrade fixture has range 50 for every upgrade, so round 1's crowd (density 0.045682 x 2 x 50 = 4.568) caps `3-0-0` (pierce 6) and `0-0-4` (pierce 8) but not `1-0-0` or `0-0-0`.
- Fixture needs by round (no camo/lead before 24): 24 camo, 28 lead, 33 camo, 36 camo, 37 camo+lead, 63 lead, 99 camo, 101 camo. Round 99 is camo (`DdtFortifiedCamo`), so a window from 97 first leaks at 99, and from 100 at 101.
- Tests about single-round behaviour pass `horizon=1`; the default window is tested explicitly.
- Invalid input raises `QueryError` (`btd6/query.py`); no rounds loaded raises `NoRoundDataError` (`btd6/rounds.py`).
- Floats are compared with `pytest.approx(rel=1e-6)`.
- Upgrades: the four Super Monkey rows of `tests/test_ranking.py::UPGRADE_STATS` (`build_database`), with costs. `0-0-4` has `can_hit_camo = 1`; the others have `0`. Pops lead: `3-0-0` (Plasma) and `0-0-4` (Normal) only.
- Rounds: bloons from `tests/fixtures/bloon_rows.json` and rounds 1-100 from `tests/fixtures/roundset_rows_1_100.csv` (`tests/income_fixture.py` helpers). `bloon_rows.json` has no property flags, so the fixture sets `has_lead = 1` on `Lead`. Real rounds used: **1** (20 Red, plain), **40** (one MOAB, `moab_share` 1.0), **63** (Lead and Ceramic, lead share 0.1197). A camo round is added as an extra round 101 holding `Blue` x10 with `is_camo = 1`.
- Medium costs: `0-0-0` 2500, `1-0-0` 4500, `3-0-0` 27000, `0-0-4` 67855.

---

## recommend

```python
def recommend(connection: sqlite3.Connection, round_number: int, money: int, difficulty: str = "medium", limit: int | None = None, horizon: int = DEFAULT_HORIZON) -> list[Recommendation]
```

Returns the affordable upgrades that can pop the round's required properties and hit camo when the round has any, ranked by round-fit score.

The caller supplies a budget, a round and options. The budget matters relative to the upgrade costs. The round matters through its kind, which decides the filters and the score weights. `difficulty` changes each cost, and `limit` truncates the result. For the receiver state, rounds or costs may not be loaded.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`money`|A) Budget relative to costs|A1: Above every cost|`100000`|
|||A2: Exactly equal to one cost|`4500`|
|||A3: Below the cheapest cost|`2499`|
|||A4: Negative|`-1`|
|||A5: Not an int|`"5000"`|
|`difficulty`|B) Difficulty|B1: Medium|`"medium"`|
|||B2: Easy|`"easy"`|
|||B3: Hard|`"hard"`|
|||B4: Impoppable|`"impoppable"`|
|||B5: Invalid|`"nightmare"`|
|`round_number`|C) Round kind|C1: Plain (no MOAB, nothing required)|`1`|
|||C2: MOAB|`40`|
|||C3: Lead and ceramic (mixed)|`63`|
|||C4: Camo|`101`|
|||C5: Not loaded|`150`|
|`limit`|D) Limit|D1: None|`None`|
|||D2: Zero|`0`|
|||D3: One|`1`|
|||D4: Larger than the result count|`10`|
|||D5: Negative|`-1`|
|`connection` (state)|E) Data loaded|E1: Upgrades, costs and rounds|full fixture|
|||E2: No rounds loaded|fixture without rounds|
|||E3: Costs not loaded|`build_database(UPGRADE_STATS, with_costs=False)` plus rounds|
|`horizon`|F) Horizon|F1: Default (5) **(Base)**|omitted|
|||F2: One|`1`|
|||F3: Longer than the loaded rounds after `round_number`|`1000` at round 100|
|||F4: Zero|`0`|
|||F5: Negative|`-3`|
|||F6: Not an int|`"5"`, `2.5`, `True`, `None`|

Base case: A1, B1, C1, D1, E1, F1

### Base Choice Coverage

| BCC Test | A | B | C | D | E | Oracle | Test Name |
|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | paths `["3-0-0", "1-0-0", "0-0-0", "0-0-4"]`, scores = decay-weighted means over rounds 1-5 (`0.020484, 0.009877, 0.008889, 0.008495`), all `first_leak_round` `None` | `test_recommend_all_base` |
| T2 | A2 | B1 | C1 | D1 | E1 | paths `["1-0-0", "0-0-0"]` (cost 4500 included; `horizon=1`) | `test_recommend_money_equal_to_cost` |
| T3 | A3 | B1 | C1 | D1 | E1 | returns `[]` | `test_recommend_money_below_cheapest` |
| T4 | A4 | B1 | C1 | D1 | E1 | raises `QueryError` | `test_recommend_negative_money` |
| T5 | A5 | B1 | C1 | D1 | E1 | raises `QueryError` | `test_recommend_money_not_int` |
| T6 | A1 | B2 | C1 | D1 | E1 | `0-0-0` has `total_cost == 2125` | `test_recommend_easy` |
| T7 | A1 | B3 | C1 | D1 | E1 | `0-0-0` has `total_cost == 2700` | `test_recommend_hard` |
| T8 | A1 | B4 | C1 | D1 | E1 | `0-0-0` has `total_cost == 3000` | `test_recommend_impoppable` |
| T9 | A1 | B5 | C1 | D1 | E1 | raises `QueryError` | `test_recommend_invalid_difficulty` |
| T10 | A1 | B1 | C2 | D1 | E1 | (`horizon=1`) paths `["0-0-0", "1-0-0", "3-0-0", "0-0-4"]`, every reasons tuple ends in `"high_single_target"` | `test_recommend_moab_round` |
| T11 | A1 | B1 | C3 | D1 | E1 | (`horizon=1`) paths `["3-0-0", "0-0-4"]`, `3-0-0` reasons `("affordable", "pops_lead", "high_pierce")` | `test_recommend_lead_round` |
| T12 | A1 | B1 | C4 | D1 | E1 | paths `["0-0-4"]`, reasons start `("affordable", "hits_camo")` | `test_recommend_camo_round` |
| T13 | A1 | B1 | C5 | D1 | E1 | raises `QueryError` | `test_recommend_round_not_loaded` |
| T14 | A1 | B1 | C1 | D2 | E1 | raises `QueryError` | `test_recommend_limit_zero` |
| T15 | A1 | B1 | C1 | D3 | E1 | paths `["3-0-0"]` | `test_recommend_limit_one` |
| T16 | A1 | B1 | C1 | D4 | E1 | four results, same as T1 (order `["3-0-0", "1-0-0", "0-0-0", "0-0-4"]`) | `test_recommend_limit_above_count` |
| T17 | A1 | B1 | C1 | D5 | E1 | raises `QueryError` | `test_recommend_negative_limit` |
| T18 | A1 | B1 | C1 | D1 | E2 | raises `NoRoundDataError` | `test_recommend_no_rounds_loaded` |
| T19 | A1 | B1 | C1 | D1 | E3 | returns `[]` | `test_recommend_costs_not_loaded` |
| T19a | A1 | B1 | C1 | D1 | E1 (F2) | `horizon=1`: scores `100*min(6, 4.568)/27000, 22.22*2/4500, 22.22/2500, 88.89*min(8, 4.568)/67855` | `test_recommend_single_round_scores_use_capped_pierce` |
| T19b | A1 | B1 | C1 | D1 | E1 (F3) | round 100: `horizon=1000` equals `horizon=2` equals `horizon=5` | `test_recommend_window_truncated_equals_exact_window` |
| T19c | A1 | B1 | C1 | D1 | E1 (F4) | raises `QueryError("horizon must be at least 1, got 0")` | `test_recommend_horizon_errors[0-...]` |
| T19d | A1 | B1 | C1 | D1 | E1 (F5) | raises `QueryError("horizon must be at least 1, got -3")` | `test_recommend_horizon_errors[-3-...]` |
| T19e | A1 | B1 | C1 | D1 | E1 (F6) | raises `QueryError("horizon must be a whole number, got '5'")` (also `2.5`, `True`, `None`) | `test_recommend_horizon_errors[...]` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T20 | `money` is a `bool` | `recommend(conn, 1, True)` raises `QueryError` | `test_recommend_money_bool` |
| T21 | `round_number` not an int | `recommend(conn, "1", 100000)` raises `QueryError` | `test_recommend_round_not_int` |
| T22 | `money = 0` boundary | returns `[]` | `test_recommend_zero_money` |
| T23 | pierce against single target (`docs/recommend.md`) | `1-0-0` before `0-0-0` in round 1, after it in round 40 | `test_recommend_pierce_flips_with_moab_share` |
| T24 | returned type | every item is a `Recommendation` with `reasons` a `tuple` starting `"affordable"` | `test_recommend_returns_recommendations` |
| T25 | equal score tie-break | two upgrades with identical stats and cost: ordered by `tower_name` then `path` | `test_recommend_tie_breaks_by_name_then_path` |
| T26 | `effective_pierce` field is the capped pierce of the current round | `0-0-0` 1, `1-0-0` 2, `3-0-0` and `0-0-4` 4.568 at round 1; `projectile_pierce` stays raw | `test_recommend_effective_pierce_field_is_capped_by_crowd` |
| T27 | `high_pierce` needs effective pierce >= 5 | round 1, `horizon=1`: no result has `high_pierce` | `test_recommend_high_pierce_needs_effective_pierce` |
| T28 | validation order | money, difficulty, limit, horizon, then round | `test_recommend_validation_order_*` |
| T29 | window score combination | `horizon=2` at round 2: `(fit_2 + 0.75 * fit_3) / 1.75`; every horizon 1-5 at round 1 equals `plain_window_score` | `test_recommend_window_two_rounds_uses_decay_weight`, `test_recommend_window_score_is_decay_weighted_mean` |
| T30 | camo leak ahead | round 100, `horizon=5`: `0-0-0`, `1-0-0`, `3-0-0` have `first_leak_round` 101 and last reason `fails_camo_at_101`; `0-0-4` none and ranks first | `test_recommend_leak_in_last_round_of_window` |
| T31 | leak zeroes the round | round 100, `horizon=2`, `0-0-0`: score `(22.22/2500) / 1.75` | `test_recommend_leak_zeroes_that_round` |
| T32 | non-leaker first even with a lower score | round 97, `horizon=5` (first camo at 99): `0-0-4` first, lower score than the leakers; leakers by score | `test_recommend_non_leakers_rank_first`, `test_recommend_leakers_ordered_by_score` |
| T33 | later property need | round 26, `horizon=3`: `0-0-0`, `1-0-0` fail lead at 28; `3-0-0`, `0-0-4` do not | `test_recommend_leak_property_needed_later` |
| T34 | `fails_*` order | round 34, `horizon=4`: `0-0-0` ends `("fails_camo_at_36", "fails_lead_at_37")`; same round (28 made camo): `("fails_camo_at_28", "fails_lead_at_28")`; each need once, at its first round | `test_recommend_fails_codes_*`, `test_recommend_each_need_reported_once_at_first_round` |
| T35 | current-round needs stay hard filters | round 37 (camo+lead): only `0-0-4` | `test_recommend_current_round_needs_stay_hard_filters` |
| T36 | invariants (hypothesis) | non-leakers first, scores non-increasing inside each group with `None` last, `fails_*` iff `first_leak_round`, `horizon=1` never leaks | `test_recommend_leak_groups_then_scores`, `test_recommend_horizon_one_never_leaks` |

---

## filters_for_threats

```python
def filters_for_threats(threats: RoundThreats) -> UpgradeFilters
```

Builds the SQL filters for a round: `can_hit_camo=True` when `camo_share > 0`, `can_pop_<prop>=True` for each property at or above `MIN_PROPERTY_SHARE`, everything else `None`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`threats.camo_share`|A) Camo present|A1: None|`0.0`|
|||A2: Some|`0.01`|
|`threats.property_share["lead"]`|B) Lead share vs `MIN_PROPERTY_SHARE`|B1: Zero|`0.0`|
|||B2: Below threshold|`0.0499`|
|||B3: Exactly at threshold|`0.05`|
|||B4: Above threshold|`0.12`|

Base case: A1, B1

### Base Choice Coverage

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | returns `UpgradeFilters()` | `test_filters_for_threats_all_base` |
| T2 | A2 | B1 | returns `UpgradeFilters(can_hit_camo=True)` | `test_filters_for_threats_camo` |
| T3 | A1 | B2 | returns `UpgradeFilters()` | `test_filters_for_threats_lead_below_threshold` |
| T4 | A1 | B3 | returns `UpgradeFilters(can_pop_lead=True)` | `test_filters_for_threats_lead_at_threshold` |
| T5 | A1 | B4 | returns `UpgradeFilters(can_pop_lead=True)` | `test_filters_for_threats_lead_above_threshold` |

---

## effective_pierce

```python
def effective_pierce(pierce: float | None, range_value: float | None, density: float | None) -> float | None
```

`min(pierce, max(1, density * 2 * range))`. `pierce` NULL/NaN gives `None`; `range` NULL/NaN or `density` `None` gives `pierce`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`pierce`|A) Pierce|A1: Number **(Base)**|`40`|
|||A2: None|`None`|
|||A3: NaN|`math.nan`|
|||A4: Below the floor of 1|`0.5`|
|`range`|B) Range|B1: Number **(Base)**|`20`|
|||B2: None|`None`|
|||B3: NaN|`math.nan`|
|`density`|C) Density|C1: Number **(Base)**|`0.0457`|
|||C2: None|`None`|
|`density`, `range`, `pierce`|D) Crowd (`density * 2 * range`) against pierce and the floor|D1: Between the floor and pierce **(Base)**|`40, 20, 0.0457` gives 1.828|
|||D2: Below the floor|`40, 20, 0.01` gives crowd 0.4, result 1|
|||D3: Zero|`40, 20, 0.0` gives 1|
|||D4: Equal to pierce|`4, 20, 0.1` gives 4|
|||D5: Above pierce|`2, 40, 0.0457` gives 2|

Base case: A1, B1, C1, D1. D is determined by the numeric values of A-C, so only D2-D5 get their own test (they change the numbers, not the null-ness).

### BCC

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | `1.828` (Ice Monkey `0-0-0`, round 1) | `test_effective_pierce[ice_monkey_round_one]` |
| T2 | A2 | B1 | C1 | - | `None` | `test_effective_pierce[null_pierce]` |
| T3 | A3 | B1 | C1 | - | `None` | `test_effective_pierce[nan_pierce]` |
| T4 | A4 | B1 | C1 | - | `0.5` (`pierce_below_floor`, density 0) | `test_effective_pierce[pierce_below_floor]` |
| T5 | A1 | B2 | C1 | - | `40` | `test_effective_pierce[null_range]` |
| T6 | A1 | B3 | C1 | - | `40` | `test_effective_pierce[nan_range]` |
| T7 | A1 | B1 | C2 | - | `40` | `test_effective_pierce[none_density]` |
| T8 | A1 | B1 | C1 | D2 | `1.0` | `test_effective_pierce[small_crowd_floors_at_one]` |
| T9 | A1 | B1 | C1 | D3 | `1.0` | `test_effective_pierce[no_crowd_floors_at_one]` |
| T10 | A1 | B1 | C1 | D4 | `4` | `test_effective_pierce[crowd_equals_pierce]` |
| T11 | A1 | B1 | C1 | D5 | `2` (Ninja Monkey `0-0-0`) | `test_effective_pierce[ninja_monkey_round_one]` |

Extra: range and density both `None` gives `pierce`; all missing gives `None`; hypothesis: result <= pierce and >= min(pierce, 1); result is non-decreasing in density (`test_effective_pierce_never_exceeds_pierce_and_keeps_floor`, `test_effective_pierce_grows_with_density`).

---

## unmet_needs

```python
def unmet_needs(row: Mapping[str, Any], threats: RoundThreats) -> tuple[str, ...]
```

The needs of `threats` (`camo` when `camo_share > 0`, then each property with share >= `MIN_PROPERTY_SHARE` in `PROPERTY_NAMES` order) that `row` does not meet (`can_hit_camo` / `can_pop_<prop>` false), in that order. `row` comes from `UpgradeRowFactory.build(...)`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`threats.camo_share`, `row.can_hit_camo`|A) Camo|A1: Not needed **(Base)**|`camo_share 0.0`, `can_hit_camo False`|
|||A2: Needed and met|`0.2`, `True`|
|||A3: Needed and unmet|`0.2`, `False`|
|||A4: Smallest positive share, unmet|`0.001`, `False`|
|`threats.property_share["lead"]`, `row.can_pop_lead`|B) Lead|B1: Not needed (zero) **(Base)**|`0.0`, `False`|
|||B2: Below threshold, unmet|`0.0499`, `False`|
|||B3: At threshold, unmet|`0.05`, `False`|
|||B4: Needed and met|`0.12`, `True`|
|`threats` shares|C) Several needs unmet|C1: One or none **(Base)**|-|
|||C2: camo, lead and black|`camo 0.3, lead 0.1, black 0.2`, all flags `False`|
|||C3: lead, glass, frozen given out of order|`frozen 0.5, glass 0.5, lead 0.5`, flags `False`|

Base case: A1, B1, C1.

### BCC

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | `()` | `test_unmet_needs[no_needs]`, `[no_needs_unmet_flags_ignored]` |
| T2 | A2 | B1 | C1 | `()` | `test_unmet_needs[camo_met]` |
| T3 | A3 | B1 | C1 | `("camo",)` | `test_unmet_needs[camo_unmet]` |
| T4 | A4 | B1 | C1 | `("camo",)` | `test_unmet_needs[camo_tiny_share_still_needed]` |
| T5 | A1 | B2 | C1 | `()` | `test_unmet_needs[lead_below_threshold]` |
| T6 | A1 | B3 | C1 | `("lead",)` | `test_unmet_needs[lead_at_threshold]` |
| T7 | A1 | B4 | C1 | `()` | `test_unmet_needs[lead_met]` |
| T8 | A1 | B1 | C2 | `("camo", "lead", "black")` | `test_unmet_needs[camo_lead_black_in_order]` |
| T9 | A1 | B1 | C3 | `("lead", "glass", "frozen")` | `test_unmet_needs[lead_glass_frozen_in_property_order]` |

Extra: camo met but lead unmet gives `("lead",)` (`only_lead_unmet`).

---

## round_score

```python
def round_score(moab_share: float, moab_dps: float | None, dps: float | None, effective_pierce: float | None, total_cost: float | None) -> float | None
```

`(moab_share x moab_dps + (1 - moab_share) x dps x effective_pierce) / total_cost`. A term with weight 0 is left out; a NULL in a weighted term, or a NULL or zero cost, gives `None`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`moab_share`|A) MOAB weight|A1: Zero|`0.0`|
|||A2: Between|`0.5`|
|||A3: One|`1.0`|
|`moab_dps`|B) MOAB DPS present|B1: Number|`30.0`|
|||B2: None|`None`|
|`dps`|C) DPS present|C1: Number|`20.0`|
|||C2: None|`None`|
|`effective_pierce`|D) Effective pierce present|D1: Number|`3.0`|
|||D2: None|`None`|
|`total_cost`|E) Cost|E1: Positive|`3000`|
|||E2: Zero|`0`|
|||E3: None|`None`|

Base case: A2, B1, C1, D1, E1

### Base Choice Coverage

| BCC Test | A | B | C | D | E | Oracle | Test Name |
|---|---|---|---|---|---|---|---|
| T1 | A2 | B1 | C1 | D1 | E1 | returns `0.015` (`(15 + 30) / 3000`) | `test_round_score_all_base` |
| T2 | A1 | B1 | C1 | D1 | E1 | returns `0.02` | `test_round_score_no_moab` |
| T3 | A3 | B1 | C1 | D1 | E1 | returns `0.01` | `test_round_score_all_moab` |
| T4 | A2 | B2 | C1 | D1 | E1 | returns `None` | `test_round_score_missing_moab_dps` |
| T5 | A2 | B1 | C2 | D1 | E1 | returns `None` | `test_round_score_missing_dps` |
| T6 | A2 | B1 | C1 | D2 | E1 | returns `None` | `test_round_score_missing_effective_pierce` |
| T7 | A2 | B1 | C1 | D1 | E2 | returns `None` | `test_round_score_zero_cost` |
| T8 | A2 | B1 | C1 | D1 | E3 | returns `None` | `test_round_score_missing_cost` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T9 | zero weight hides a NULL (A1 with B2) | `round_score(0.0, None, 20.0, 3.0, 3000)` returns `0.02` | `test_round_score_zero_weight_ignores_missing_moab` |
| T10 | zero weight hides NULLs (A3 with C2 and/or D2) | `round_score(1.0, 30.0, None, 3.0, 3000)`, `(1.0, 30.0, 20.0, None, 3000)` and both `None` return `0.01` | `test_round_score_zero_weight_ignores_missing_pierce_terms` |
| T11 | the capped pierce is used as given | `round_score(0.0, 30.0, 20.0, 1.83, 3000)` = `20 * 1.83 / 3000` | `test_round_score_uses_effective_pierce_not_raw` |

---

## reasons_for

```python
def reasons_for(threats: RoundThreats, moab_dps: float | None, dps: float | None, effective_pierce: float | None) -> tuple[str, ...]
```

Reason codes in order: `affordable`, `hits_camo` when the round has camo, `pops_<prop>` for each required property, then at most one of `high_pierce` / `high_single_target` (see `docs/recommend.md`). `moab_term = moab_share x moab_dps`, `pierce_term = (1 - moab_share) x dps x effective_pierce`; the `fails_*` codes are added by the caller, not here.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`threats`|A) Round requirements|A1: None|`camo_share 0`, all property shares `0`|
|||A2: Camo|`camo_share 0.2`|
|||A3: Lead required|`property_share["lead"] 0.12`|
|`threats.moab_share` with DPS|B) Dominant term|B1: Pierce term larger|`moab_share 0.0`, `moab_dps 10`, `dps 12` (pierce term 60)|
|||B2: MOAB term larger|`moab_share 1.0`, `moab_dps 10`, `dps 12`|
|||B3: Terms equal|`moab_share 0.5`, `moab_dps 60`, `dps 12` (30 against 30)|
|`effective_pierce`|C) Effective pierce vs `HIGH_PIERCE`|C1: At threshold|`5`|
|||C2: Below|`4` (with `dps 15`)|
|||C3: None|`None`|

Base case: A1, B1, C1

### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | `("affordable", "high_pierce")` | `test_reasons_for_all_base` |
| T2 | A2 | B1 | C1 | `("affordable", "hits_camo", "high_pierce")` | `test_reasons_for_camo` |
| T3 | A3 | B1 | C1 | `("affordable", "pops_lead", "high_pierce")` | `test_reasons_for_lead` |
| T4 | A1 | B2 | C1 | `("affordable", "high_single_target")` | `test_reasons_for_single_target` |
| T5 | A1 | B3 | C1 | `("affordable",)` | `test_reasons_for_equal_terms` |
| T6 | A1 | B1 | C2 | `("affordable",)` | `test_reasons_for_low_effective_pierce` |
| T7 | A1 | B1 | C3 | `("affordable",)` | `test_reasons_for_missing_effective_pierce` |

Extra: effective pierce 4.999 gives no `high_pierce` (`test_reasons_for_effective_pierce_just_below_threshold`); a NULL `moab_dps` counts as 0 so `high_pierce` stays; a NULL `dps` counts as 0 so `high_single_target` stays.

---

## sort_key

```python
def sort_key(item: Recommendation) -> tuple
```

Leak group first (`first_leak_round is None` before a number), then score descending with `None` last, then `total_cost`, `tower_name`, `path`.

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T1 | score 0.0 against `None` | `0.0` before `None` | `test_sort_key_zero_score_before_missing` |
| T2 | leak group beats score | non-leaker (0.1) before leaker (9.0) | `test_sort_key_non_leaker_before_leaker_with_higher_score` |
| T3 | leak group beats NULL score | non-leaker with `None` before leaker with 9.0 | `test_sort_key_non_leaker_with_missing_score_before_leaker` |
| T4 | inside the leak group | higher score first whatever the leak round | `test_sort_key_leakers_ordered_by_score` |

---

## Callers (`horizon` and the new fields)

| Caller | Test | Oracle |
|---|---|---|
| CLI `recommend --horizon H` | `tests/test_cli_recommend.py` | header `rank tower path cost score leaks at reasons`; round 100 default horizon: `0-0-4` blank, others `101`, reasons end `fails_camo_at_101`; `--horizon 1` leaves the column blank; `--horizon 0` exits 2 with `horizon must be at least 1, got 0`; `--horizon abc` is an argparse error. Other CLI tests pass `--horizon 1` |
| API `GET /api/recommendations?horizon=H` | `tests/test_api_recommendations.py` | rows carry `effective_pierce` and `first_leak_round`; default equals `recommend(...)`; `horizon=0` and `horizon=abc` give 422 with the `QueryError` message |
| `form_to_recommend_options` | `tests/test_api_params_recommend.py` | `RecommendOptions.horizon`: blank gives `DEFAULT_HORIZON`, `"3"` gives 3, `"0"`/`"abc"`/`"1.5"` raise `QueryError` |
| agent tool `recommend` | `tests/test_agent_tools.py` | schema has optional integer `horizon` with `minimum` 1; `horizon=1` against `5` changes `first_leak_round` at round 100; `0` and `"5"` give a `QueryError` result; rows have the two new keys |

---

## Acceptance and property tests (#122)

Use the full fixture (all resolved tower fixtures under `tests/fixtures/` loaded with `btd6.db.loader`, Super Monkey costs served for every tower via `offline_costs_wiki`, rounds 1-100 with `has_lead` set on `Lead`), or the four-upgrade fixture where noted.

| Test | Oracle | Test Name |
|---|---|---|
| A1 | round 63, `money 100000`: every result can pop lead (`pops_lead` in `reasons`); none requires camo because the round has none | `test_recommend_round_63_pops_lead` |
| A2 | `horizon=1`: mean `projectile_pierce` of the top 5 for round 63 > mean of the top 5 for round 40 (`money 100000`) | `test_recommend_round_63_prefers_pierce` |
| A3 | `horizon=1`: top result's `moab_dps / total_cost` for round 40 >= the same for round 63's top result (the score is per dollar, so raw `moab_dps` would favour round 63's pricier pick) | `test_recommend_round_40_prefers_single_target` |
| A4 | hypothesis: `money_a <= money_b` in `0..200000`, any round in `{1, 40, 63}` → `{(t, p)}` for `money_a` ⊆ for `money_b` | `test_recommend_budget_monotonic` |
| A5 | hypothesis: every result has `total_cost <= money` | `test_recommend_never_exceeds_money` |
| A6 | hypothesis: leakers after non-leakers; inside each group scores are non-increasing with `None` last (any `horizon` 1-6) | `test_recommend_sorted_by_leak_group_then_score` |
| A7 | round 1, money 5000: Ice Monkey `0-0-0` is returned but is not first; its `effective_pierce` is `2 * 20 * density(1)` (below 2) although `projectile_pierce` is 40 | `test_recommend_round_1_does_not_pick_ice_monkey_base` |
| A8 | round 20, money 5000, `horizon=5`: the top result has `first_leak_round` `None`, no `fails_*` reason and can hit camo; every leaker leaks at 24 and cannot hit camo | `test_recommend_round_20_prefers_camo_capable_upgrade` |
| A9 | round 20, money 5000, `horizon=1`: nobody leaks; the top result cannot hit camo | `test_recommend_round_20_single_round_ignores_later_camo` |

The full fixture serves Super Monkey costs for every tower (`0-0-0` costs 2500), so the money values 650 from the real data become 5000 here.

---

## recommend: `owned` and `one_per_tower`

```python
def recommend(connection, round_number, money, difficulty="medium", limit=None, horizon=DEFAULT_HORIZON, owned: Sequence[OwnedTower] | None = None, one_per_tower: bool = False) -> list[Recommendation]
```

`OwnedTower(tower_name, path)` is a `NamedTuple` in `btd6/recommend.py`. Owned towers add upgrade candidates (price `cost(Q) - cost(P)`), and cover needs (camo, properties) so they are dropped from filters, leaks and reason codes. `one_per_tower` keeps the first result of each tower name after sorting and before `limit`. Also assumed: `filters_for_threats(threats, covered)` takes a collection of need names; `Recommendation.upgrade_from` follows `total_cost`; `sort_key` ends with "new purchase before upgrade". Oracles: `tests/recommend_fixture.py` (`fixture_value`, `upgrade_window_score`, `reachable_paths`, `upgrade_price`), written independently of `btd6/`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`owned`|A) Entries|A1: None or empty|`None`, `()`|
|||A2: One known entry|`[OwnedTower("Super Monkey", "0-0-0")]`|
|||A3: Several known entries|`0-0-0` and `1-0-0`|
|||A4: Duplicate entries|`0-0-0` three times|
|||A5: Entry the database does not have|`("Banana Farm", "2-0-0")`, `("Super Monkey", "2-0-0")`|
|||A6: Bad path|`("Super Monkey", "1-2")`|
|`owned`|B) Owned upgrade's tier position|B1: Upgrades reachable (`0-0-0`)|`1-0-0`, `3-0-0`, `0-0-4`|
|||B2: One reachable (`1-0-0`)|`3-0-0`|
|||B3: None reachable (`3-0-0`, `0-0-4`)|`[]`|
|`owned`, `round_number`|C) Needs the owned towers cover|C1: None covered|owned `0-0-0` at round 63 (lead)|
|||C2: All current needs covered|owned `0-0-4` at round 101 (camo), `3-0-0` at round 63 (lead)|
|||C3: One of two needs covered|owned `3-0-0` at round 37 (camo and lead)|
|||C4: Covered need only in a later round|owned `0-0-4`, window 22-24 (camo at 24)|
|`money`|D) Money against the upgrade price|D1: At or above the price|`2000` for `0-0-0 -> 1-0-0`|
|||D2: Below the price but above the new cost? (price is lower than cost)|`1999`: nothing|
|`one_per_tower`|E) Value|E1: `False`|`False`|
|||E2: `True`, one tower in the database|`True` (Super Monkey only)|
|||E3: `True`, several towers|`True`, full database|
|||E4: Not a bool|`"yes"`, `1`, `None`|
|`limit` with `one_per_tower`|F) Order of limit and uniqueness|F1: No limit|`None`|
|||F2: Limit below the number of towers|`limit=3`, `True`, full database|

Base case: A2, B1, C1, D1, E1, F1

### Base Choice Coverage

| BCC Test | A | B | C | D | E | F | Oracle | Test Name |
|---|---|---|---|---|---|---|---|---|
| T1 | A2 | B1 | C1 | D1 | E1 | F1 | upgrades `1-0-0` (2000), `3-0-0` (24500), `0-0-4` (65355) with `upgrade_from` `0-0-0`, reasons `affordable, upgrades_owned, ...`; four new purchases still present | `test_recommend_owned_candidate_set`, `test_recommend_owned_new_purchases_are_still_offered` |
| T2 | A1 | B1 | C1 | D1 | E1 | F1 | equals the default call, every `upgrade_from` is `None` | `test_recommend_owned_nothing_is_the_same_as_default` |
| T3 | A3 | B1 | C1 | D1 | E1 | F1 | candidates from both owned paths: `3-0-0` for 24500 and 22500 | `test_recommend_owned_two_paths_give_two_candidates_for_one_upgrade` |
| T4 | A4 | B1 | C1 | D1 | E1 | F1 | same as one entry | `test_recommend_owned_duplicates_give_one_set_of_candidates` |
| T5 | A5 | B1 | C1 | D1 | E1 | F1 | ignored: same as no owned | `test_recommend_owned_unknown_entry_is_ignored` |
| T6 | A6 | B1 | C1 | D1 | E1 | F1 | `QueryError` `owned path must be X-Y-Z, got '1-2'` (also `6-0-0`, `abc`, `""`) | `test_recommend_owned_path_must_be_x_y_z` |
| T7 | A2 | B2 | C1 | D1 | E1 | F1 | only `3-0-0` for 22500 | `test_recommend_owned_candidate_set[1-0-0]` |
| T8 | A2 | B3 | C1 | D1 | E1 | F1 | no upgrades | `test_recommend_owned_candidate_set[3-0-0]`, `[0-0-4]` |
| T9 | A2 | B1 | C2 | D1 | E1 | F1 | round 101: all four purchases, no `hits_camo`; round 63 with `3-0-0`: no `pops_lead` | `test_recommend_owned_camo_covered_makes_every_upgrade_eligible`, `test_recommend_owned_lead_covered_drops_the_lead_filter` |
| T10 | A2 | B1 | C3 | D1 | E1 | F1 | round 37: only `0-0-4`, reasons `affordable, hits_camo` | `test_recommend_owned_covers_one_need_and_keeps_the_other` |
| T11 | A2 | B1 | C4 | D1 | E1 | F1 | no `first_leak_round`, no `fails_*` | `test_recommend_owned_camo_covered_removes_later_leaks` |
| T12 | A2 | B1 | C1 | D2 | E1 | F1 | money 1999: `[]`; 2000: `1-0-0` only; 24500 adds `3-0-0` | `test_recommend_owned_affordability_uses_price` |
| T13 | A2 | B1 | C1 | D1 | E2 | F1 | one result, equal to the first of the full list (upgrade and purchase share a tower) | `test_recommend_one_per_tower_upgrade_and_purchase_share_a_tower` |
| T14 | A2 | B1 | C1 | D1 | E3 | F1 | unique tower names, equal to first-per-tower of the full list | `test_recommend_one_per_tower_without_limit_has_unique_names` |
| T15 | A2 | B1 | C1 | D1 | E4 | F1 | `QueryError` `one_per_tower must be true or false, got 'yes'` | `test_recommend_one_per_tower_must_be_a_bool` |
| T16 | A2 | B1 | C1 | D1 | E3 | F2 | first three towers of the unique list, not the first three results | `test_recommend_one_per_tower_applies_before_limit` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T17 | score oracle | `(value(Q) - value(P)) / price`, decay-weighted over windows `1/1`, `1/4`, `20/4`, `26/3` (lead leak at 28), `63/1` | `test_recommend_owned_score_is_decay_weighted_mean_of_value_gain_per_price` |
| T18 | owned tower with an unmet need has value 0 | round 63, `0-0-0 -> 3-0-0`: `score = value(3-0-0) / 24500` | `test_recommend_owned_score_uses_zero_value_for_owned_with_unmet_need` |
| T19 | upgrade leaks | window 26-28, `0-0-0 -> 1-0-0`: `first_leak_round` 28, last reason `fails_lead_at_28`, sorted after non-leakers | `test_recommend_owned_upgrade_leaks_when_a_later_round_needs_more` |
| T20 | multi-tower coverage | Ninja Monkey `0-0-0` covers camo: Dart Monkey `0-0-0` is returned at round 24 without `hits_camo` and without leaks | `test_recommend_owned_other_tower_covers_camo`, `test_recommend_owned_other_tower_removes_camo_leak` |
| T21 | owned tower without the need | Dart Monkey `0-0-0` changes no new purchase | `test_recommend_owned_tower_without_the_need_changes_no_purchase` |
| T22 | validation order | `horizon`, then `owned`, then `one_per_tower`, then the round | `test_recommend_validation_order_*` |
| T23 | `Recommendation` fields, `sort_key` | `upgrade_from` follows `total_cost`; new purchase before upgrade on a full tie; negative scores between positive and `None` | `test_recommendation_fields_put_upgrade_from_after_total_cost`, `test_sort_key_*` |
| T24 | `filters_for_threats(threats, covered)` | covered needs give `None`/absent filters | `test_filters_for_threats_drops_covered_needs` |
| T25 | hypothesis | every result affordable by price, `upgrades_owned` iff `upgrade_from`, upgrade reachable from an owned path, `one_per_tower` gives at most one result in the single-tower database and the first of the full list, owned order and duplicates do not matter | `test_recommend_owned_invariants`, `test_recommend_owned_is_order_and_duplicate_independent` |

D2 note: the price is always lower than the new cost of the same upgrade, so affordability by price is tested at the boundaries `1999`, `2000`, `24499`, `24500`.
