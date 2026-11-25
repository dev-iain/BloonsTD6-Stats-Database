# Round threats: `round_threats`

## Rules for these tests

- Lives in `btd6/threats.py`; formulas in `docs/threats.md`. Tests build rounds with `tests/rounds_fixture.py` (extended with the property flags) and never read `btd6.db`, except the acceptance tests for rounds 40 and 63, which skip when the database is not loaded.
- Group RBE = `count * rbe`, or `count * rbe_fort` when `is_fortified` and `rbe_fort` is not NULL. A group whose RBE cannot be computed (NULL `rbe`) is excluded from every total and share and counted in `unknown_groups`.
- `total_rbe` is the sum of known group RBE (int). Every share is `RBE of matching groups / total_rbe`, a float in `0..1`; with `total_rbe == 0` every share and `mean_layers` is `0.0`.
- `property_share` has the six keys `lead, black, white, purple, glass, frozen`. `camo_share` uses `is_camo`, `regrow_share` uses `is_regrow`, `moab_share` uses `is_moab`. A group counts toward every property its bloon has.
- `mean_layers` = sum(group RBE * `bloons.layers`) / `total_rbe`, i.e. RBE-weighted.
- Validation is `validate_round`: `NoRoundDataError` when no rounds are loaded, `ValueError` for a round below 1 or above the highest loaded, `TypeError` for a non-int (including `bool`).
- Pop rule (for the later recommender): an upgrade can pop bloon B iff for every property B has, the upgrade's `can_pop_<property>` is true.

---

## round_threats

```python
def round_threats(connection: sqlite3.Connection, round_number: int) -> RoundThreats
```

`RoundThreats(round, total_rbe, unknown_groups, property_share, camo_share, regrow_share, moab_share, mean_layers, crowd_density=None)`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`round_number`, database|A) Round kind|A1: Mixed **(Base)**|round 3: Red x5, Blue x3, Lead x2 (Lead has `has_lead`)|
|||A2: Empty groups|round 5 with a `rounds` row and no groups|
|||A3: Only camo|round 24: Blue x10, camo|
|||A4: Only lead|round 27: Lead x6|
|||A5: MOAB-only|round 40 variant: Moab x1|
|`round_number`, database|B) Group modifiers|B1: Plain **(Base)**|`is_fortified = 0`, `is_regrow = 0`|
|||B2: Fortified group|Lead x6 with `is_fortified = 1` (`rbe_fort` 30)|
|||B3: Regrow group|Blue x10 with `is_regrow = 1`|
|`round_number`, database|C) Group RBE|C1: Known **(Base)**|`rbe` set on every bloon|
|||C2: NULL `rbe` on a group|bloon inserted with `rbe` NULL|
|||C3: Fortified with NULL `rbe_fort`|Lead x6 fortified, `rbe_fort` NULL|
|`round_number`|D) Validity|D1: In range **(Base)**|`3`|
|||D2: Below 1|`0`|
|||D3: Above loaded data|`41` (40 loaded)|
|||D4: No rounds loaded|empty database|
|||D5: Wrong type|`"3"`, `True`, `3.0`|

Base case: A1, B1, C1, D1

### BCC

Base fixture: rounds 1-40 as in `tests/rounds_fixture.py`; round 3 is `[Red x5, Blue x3, Lead x2]` (RBE 1, 2, 23): `total_rbe = 5 + 6 + 46 = 57`.

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | `total_rbe` 57, `unknown_groups` 0, `property_share["lead"]` = 46/57, other five properties 0.0, `camo_share` 0.0, `moab_share` 0.0, `mean_layers` = (5\*1\*layers(Red) + 6\*layers(Blue) + 46\*layers(Lead)) / 57 | `test_round_threats_mixed_round` |
| T2 | A2 | B1 | C1 | D1 | `total_rbe` 0, `unknown_groups` 0, all shares and `mean_layers` 0.0 | `test_round_threats_empty_round` |
| T3 | A3 | B1 | C1 | D1 | `camo_share` 1.0, `property_share["lead"]` 0.0 | `test_round_threats_only_camo` |
| T4 | A4 | B1 | C1 | D1 | `property_share["lead"]` 1.0, `camo_share` 0.0 | `test_round_threats_only_lead` |
| T5 | A5 | B1 | C1 | D1 | `moab_share` 1.0, `total_rbe` 616 | `test_round_threats_moab_only` |
| T6 | A1 | B2 | C1 | D1 | the fortified Lead group counts `count * rbe_fort` | `test_round_threats_fortified_uses_rbe_fort` |
| T7 | A1 | B3 | C1 | D1 | `regrow_share` = regrow RBE / `total_rbe` | `test_round_threats_regrow_share` |
| T8 | A1 | B1 | C2 | D1 | group excluded: `unknown_groups` 1, shares computed from the other groups | `test_round_threats_null_rbe_group` |
| T9 | A1 | B1 | C3 | D1 | fortified group with NULL `rbe_fort` falls back to `rbe` (same as `docs/data-notes.md` `COALESCE`) | `test_round_threats_fortified_null_rbe_fort` |
| T10 | A1 | B1 | C1 | D2 | raises `ValueError` | `test_round_threats_round_below_one` |
| T11 | A1 | B1 | C1 | D3 | raises `ValueError` ("not loaded") | `test_round_threats_round_above_loaded` |
| T12 | A1 | B1 | C1 | D4 | raises `NoRoundDataError` | `test_round_threats_no_round_data` |
| T13 | A1 | B1 | C1 | D5 | raises `TypeError` (`"3"`, `True`, `3.0`) | `test_round_threats_wrong_type` |

Extra (not BCC): a round whose only group has NULL `rbe` gives `total_rbe` 0 and `unknown_groups` 1 (C2 with only that group); hypothesis test: every share is within 0..1 and `moab_share` equals the MOAB RBE from `get_round` divided by `total_rbe`; acceptance tests for rounds 40 (`moab_share > 0`) and 63 (`camo_share > 0`, lead share the largest property share) on the real database.

---

## crowd_density

```python
RoundThreats.crowd_density: float | None  # default None, last field
MIN_GROUP_SECONDS = 1.0
```

`sum(group RBE * density_g) / sum(group RBE)` with `density_g = (count / max(duration, MIN_GROUP_SECONDS)) / bloons.speed`. A group with no RBE or a NULL/0 `speed` is left out of both sums; `None` when no group is left (`docs/threats.md`). Tests: `tests/test_threats_density.py`; the fixture of `tests/rounds_fixture.py` has speed NULL and duration 1, so each test sets them with `UPDATE`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|round groups, database|A) Usable groups|A1: One group **(Base)**|round 1: Red x20, duration 17.5125, `speed` 25|
|||A2: Several groups, different RBE|round 3: Red x5 (speed 25), Blue x3 (speed 50), Lead x2 (speed 25), duration 10 each|
|||A3: A group with NULL `speed`|round 3 with Blue `speed` NULL|
|||A4: A group with `speed` 0|round 3 with Blue `speed` 0|
|||A5: A group with NULL `rbe`|round 3 with Blue `rbe` NULL|
|||A6: No usable group (speed NULL everywhere)|round 3 with no `speed` set|
|||A7: Only group has NULL `rbe`|round 27 (Lead x6), `speed` 25, `rbe` NULL|
|||A8: Round without groups|round 5 with its groups deleted|
|`duration`|B) Group duration against `MIN_GROUP_SECONDS`|B1: Above **(Base)**|`17.5125`|
|||B2: Exactly equal|`1.0`|
|||B3: Below|`0.5`|
|||B4: Zero|`0.0`|
|`RoundThreats` construction|C) `crowd_density` argument|C1: Omitted **(Base)**|`RoundThreatsFactory.build()`|
|||C2: Given|`crowd_density=0.25`|

Base case: A1, B1, C1 (C is only varied in the constructor test).

### BCC

Oracles use `(count / max(duration, 1)) / speed`; B2-B4 use round 40 Moab x1 (`speed` 25).

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | `crowd_density` = (20 / 17.5125) / 25 = 0.045682 | `test_round_threats_crowd_density_round_one` |
| T2 | A2 | B1 | C1 | RBE-weighted: (5\*0.02 + 6\*0.006 + 46\*0.008) / 57, not the plain mean of the three densities | `test_round_threats_crowd_density_rbe_weighting` |
| T3 | A3 | B1 | C1 | Blue left out: (5\*0.02 + 46\*0.008) / 51; `total_rbe` still 57 | `test_round_threats_crowd_density_leaves_out_unusable_speed[NULL]` |
| T4 | A4 | B1 | C1 | same as T3 | `test_round_threats_crowd_density_leaves_out_unusable_speed[0]` |
| T5 | A5 | B1 | C1 | Blue left out, same oracle as T3 | `test_round_threats_crowd_density_leaves_out_null_rbe` |
| T6 | A6 | B1 | C1 | `None` | `test_round_threats_crowd_density_no_speeds_is_none` |
| T7 | A7 | B1 | C1 | `None` | `test_round_threats_crowd_density_only_unknown_group_is_none` |
| T8 | A8 | B1 | C1 | `None` | `test_round_threats_crowd_density_empty_round_is_none` |
| T9 | A1 | B2 | C1 | 0.04 (1 / 1 / 25) | `test_round_threats_crowd_density_duration_clamp[1.0-0.04]` |
| T10 | A1 | B3 | C1 | 0.04 (clamped to 1 s) | `test_round_threats_crowd_density_duration_clamp[0.5-0.04]` |
| T11 | A1 | B4 | C1 | 0.04 (clamped to 1 s) | `test_round_threats_crowd_density_duration_clamp[0.0-0.04]` |
| T12 | A1 | B1 | C2 | `RoundThreatsFactory.build(crowd_density=0.25).crowd_density == 0.25`; omitted gives `None` | `test_round_threats_crowd_density_defaults_to_none` |

Extra (not BCC): `duration` 2.0 gives 0.02 (`...duration_clamp[2.0-0.02]`); `MIN_GROUP_SECONDS == 1.0` (`test_min_group_seconds`); hypothesis: with random speeds and durations the density lies between the smallest and largest group density (`test_round_threats_crowd_density_between_group_densities`).
