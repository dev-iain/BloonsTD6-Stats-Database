# Recommender: `recommend`, `filters_for_threats`, `round_score`, `reasons_for`

## Rules for these tests

- Rules, constants, NULL handling and tie order are defined in `docs/recommend.md`.
- Invalid input raises `QueryError` (`btd6/query.py`); no rounds loaded raises `NoRoundDataError` (`btd6/rounds.py`).
- Floats are compared with `pytest.approx(rel=1e-6)`.
- Upgrades: the four Super Monkey rows of `tests/test_ranking.py::UPGRADE_STATS` (`build_database`), with costs. `0-0-4` has `can_hit_camo = 1`; the others have `0`. Pops lead: `3-0-0` (Plasma) and `0-0-4` (Normal) only.
- Rounds: bloons from `tests/fixtures/bloon_rows.json` and rounds 1-100 from `tests/fixtures/roundset_rows_1_100.csv` (`tests/income_fixture.py` helpers). `bloon_rows.json` has no property flags, so the fixture sets `has_lead = 1` on `Lead`. Real rounds used: **1** (20 Red, plain), **40** (one MOAB, `moab_share` 1.0), **63** (Lead and Ceramic, lead share 0.1197). A camo round is added as an extra round 101 holding `Blue` x10 with `is_camo = 1`.
- Medium costs: `0-0-0` 2500, `1-0-0` 4500, `3-0-0` 27000, `0-0-4` 67855.

---

## recommend

```python
def recommend(connection: sqlite3.Connection, round_number: int, money: int, difficulty: str = "medium", limit: int | None = None) -> list[Recommendation]
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

Base case: A1, B1, C1, D1, E1

### Base Choice Coverage

| BCC Test | A | B | C | D | E | Oracle | Test Name |
|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | paths `["3-0-0", "0-0-4", "1-0-0", "0-0-0"]`, scores `0.0222222, 0.0104799, 0.00987654, 0.00888889` | `test_recommend_all_base` |
| T2 | A2 | B1 | C1 | D1 | E1 | paths `["1-0-0", "0-0-0"]` (cost 4500 included) | `test_recommend_money_equal_to_cost` |
| T3 | A3 | B1 | C1 | D1 | E1 | returns `[]` | `test_recommend_money_below_cheapest` |
| T4 | A4 | B1 | C1 | D1 | E1 | raises `QueryError` | `test_recommend_negative_money` |
| T5 | A5 | B1 | C1 | D1 | E1 | raises `QueryError` | `test_recommend_money_not_int` |
| T6 | A1 | B2 | C1 | D1 | E1 | `0-0-0` has `total_cost == 2125` | `test_recommend_easy` |
| T7 | A1 | B3 | C1 | D1 | E1 | `0-0-0` has `total_cost == 2700` | `test_recommend_hard` |
| T8 | A1 | B4 | C1 | D1 | E1 | `0-0-0` has `total_cost == 3000` | `test_recommend_impoppable` |
| T9 | A1 | B5 | C1 | D1 | E1 | raises `QueryError` | `test_recommend_invalid_difficulty` |
| T10 | A1 | B1 | C2 | D1 | E1 | paths `["0-0-0", "1-0-0", "3-0-0", "0-0-4"]`, every reasons tuple ends in `"high_single_target"` | `test_recommend_moab_round` |
| T11 | A1 | B1 | C3 | D1 | E1 | paths `["3-0-0", "0-0-4"]`, `3-0-0` reasons `("affordable", "pops_lead", "high_pierce")` | `test_recommend_lead_round` |
| T12 | A1 | B1 | C4 | D1 | E1 | paths `["0-0-4"]`, reasons start `("affordable", "hits_camo")` | `test_recommend_camo_round` |
| T13 | A1 | B1 | C5 | D1 | E1 | raises `QueryError` | `test_recommend_round_not_loaded` |
| T14 | A1 | B1 | C1 | D2 | E1 | raises `QueryError` | `test_recommend_limit_zero` |
| T15 | A1 | B1 | C1 | D3 | E1 | paths `["3-0-0"]` | `test_recommend_limit_one` |
| T16 | A1 | B1 | C1 | D4 | E1 | four results, same as T1 | `test_recommend_limit_above_count` |
| T17 | A1 | B1 | C1 | D5 | E1 | raises `QueryError` | `test_recommend_negative_limit` |
| T18 | A1 | B1 | C1 | D1 | E2 | raises `NoRoundDataError` | `test_recommend_no_rounds_loaded` |
| T19 | A1 | B1 | C1 | D1 | E3 | returns `[]` | `test_recommend_costs_not_loaded` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T20 | `money` is a `bool` | `recommend(conn, 1, True)` raises `QueryError` | `test_recommend_money_bool` |
| T21 | `round_number` not an int | `recommend(conn, "1", 100000)` raises `QueryError` | `test_recommend_round_not_int` |
| T22 | `money = 0` boundary | returns `[]` | `test_recommend_zero_money` |
| T23 | pierce against single target (`docs/recommend.md`) | `1-0-0` before `0-0-0` in round 1, after it in round 40 | `test_recommend_pierce_flips_with_moab_share` |
| T24 | returned type | every item is a `Recommendation` with `reasons` a `tuple` starting `"affordable"` | `test_recommend_returns_recommendations` |
| T25 | equal score tie-break | two upgrades with identical stats and cost: ordered by `tower_name` then `path` | `test_recommend_tie_breaks_by_name_then_path` |

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

## round_score

```python
def round_score(moab_share: float, moab_dps: float | None, pierce_weighted_dps: float | None, total_cost: float | None) -> float | None
```

`(moab_share × moab_dps + (1 − moab_share) × pierce_weighted_dps) / total_cost`. A term with weight 0 is left out; a NULL in a weighted term, or a NULL or zero cost, gives `None`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`moab_share`|A) MOAB weight|A1: Zero|`0.0`|
|||A2: Between|`0.5`|
|||A3: One|`1.0`|
|`moab_dps`|B) MOAB DPS present|B1: Number|`30.0`|
|||B2: None|`None`|
|`pierce_weighted_dps`|C) Pierce DPS present|C1: Number|`60.0`|
|||C2: None|`None`|
|`total_cost`|D) Cost|D1: Positive|`3000`|
|||D2: Zero|`0`|
|||D3: None|`None`|

Base case: A2, B1, C1, D1

### Base Choice Coverage

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A2 | B1 | C1 | D1 | returns `0.015` (`(15 + 30) / 3000`) | `test_round_score_all_base` |
| T2 | A1 | B1 | C1 | D1 | returns `0.02` | `test_round_score_no_moab` |
| T3 | A3 | B1 | C1 | D1 | returns `0.01` | `test_round_score_all_moab` |
| T4 | A2 | B2 | C1 | D1 | returns `None` | `test_round_score_missing_moab_dps` |
| T5 | A2 | B1 | C2 | D1 | returns `None` | `test_round_score_missing_pierce_dps` |
| T6 | A2 | B1 | C1 | D2 | returns `None` | `test_round_score_zero_cost` |
| T7 | A2 | B1 | C1 | D3 | returns `None` | `test_round_score_missing_cost` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T8 | zero weight hides a NULL (A1 with B2) | `round_score(0.0, None, 60.0, 3000)` returns `0.02` | `test_round_score_zero_weight_ignores_missing_moab` |
| T9 | zero weight hides a NULL (A3 with C2) | `round_score(1.0, 30.0, None, 3000)` returns `0.01` | `test_round_score_zero_weight_ignores_missing_pierce` |

---

## reasons_for

```python
def reasons_for(threats: RoundThreats, moab_dps: float | None, pierce_weighted_dps: float | None, projectile_pierce: float | None) -> tuple[str, ...]
```

Reason codes in order: `affordable`, `hits_camo` when the round has camo, `pops_<prop>` for each required property, then at most one of `high_pierce` / `high_single_target` (see `docs/recommend.md`).

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`threats`|A) Round requirements|A1: None|`camo_share 0`, all property shares `0`|
|||A2: Camo|`camo_share 0.2`|
|||A3: Lead required|`property_share["lead"] 0.12`|
|`threats.moab_share` with DPS|B) Dominant term|B1: Pierce term larger|`moab_share 0.0`, `moab_dps 10`, `pierce_weighted_dps 60`|
|||B2: MOAB term larger|`moab_share 1.0`, `moab_dps 10`, `pierce_weighted_dps 60`|
|||B3: Terms equal|`moab_share 0.5`, `moab_dps 60`, `pierce_weighted_dps 60`|
|`projectile_pierce`|C) Pierce vs `HIGH_PIERCE`|C1: At threshold|`5`|
|||C2: Below|`4`|
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
| T6 | A1 | B1 | C2 | `("affordable",)` | `test_reasons_for_low_pierce` |
| T7 | A1 | B1 | C3 | `("affordable",)` | `test_reasons_for_missing_pierce` |

---

## Acceptance and property tests (#122)

Use the full fixture (all resolved tower fixtures under `tests/fixtures/` loaded with `btd6.db.loader`, Super Monkey costs served for every tower via `offline_costs_wiki`, rounds 1-100 with `has_lead` set on `Lead`), or the four-upgrade fixture where noted.

| Test | Oracle | Test Name |
|---|---|---|
| A1 | round 63, `money 100000`: every result can pop lead (`pops_lead` in `reasons`); none requires camo because the round has none | `test_recommend_round_63_pops_lead` |
| A2 | mean `projectile_pierce` of the top 5 for round 63 > mean of the top 5 for round 40 (`money 100000`) | `test_recommend_round_63_prefers_pierce` |
| A3 | top result's `moab_dps / total_cost` for round 40 >= the same for round 63's top result (the score is per dollar, so raw `moab_dps` would favour round 63's pricier pick) | `test_recommend_round_40_prefers_single_target` |
| A4 | hypothesis: `money_a <= money_b` in `0..200000`, any round in `{1, 40, 63}` → `{(t, p)}` for `money_a` ⊆ for `money_b` | `test_recommend_budget_monotonic` |
| A5 | hypothesis: every result has `total_cost <= money` | `test_recommend_never_exceeds_money` |
| A6 | hypothesis: scores are non-increasing, with `None` only at the end | `test_recommend_sorted_by_score` |
