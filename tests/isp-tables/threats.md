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

`RoundThreats(round, total_rbe, unknown_groups, property_share, camo_share, regrow_share, moab_share, mean_layers)`.

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
