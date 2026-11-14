# Example: `extract_row(code: str, stats: dict) -> dict`

Take the function `extract_row(code, stats)` in `btd6/etl/extract.py`, whose ISP is provided below. First, we use interface-based modeling; we know that the function takes in the parameters `code` and `stats`, thus we model the different characteristics of each. To determine important characteristics, we first fixate on the function of the code: the caller wants one flat row describing an upgrade, including which bloon types its first projectile can pop. We know that the `immuneBloonProperties` bitmask on the projectile directly decides the `damage_type` and every `can_pop_*` flag, thus we first model the value of `immuneBloonProperties`, including the missing key, a single immunity, several immunities and a mask that is not in `DAMAGE_TYPES`. The expected `can_pop_*` flags are the functional outcome of that bitmask, so they are checked in the oracle instead of being modeled as a characteristic of their own. Next, we know that the function walks `attacks -> projectiles` through `_order` lists with `first_of`, so we model the structure of `stats`: an upgrade with no attacks at all (or an attack with no projectiles) must still return a row instead of raising. For `code`, the only behavior is conversion to a path (`_023` becomes `0-2-3`), so we model only whether the code is the base upgrade (all zeros) or a purchased upgrade.

## ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`stats` (projectile)|A) `immuneBloonProperties`|A1: Key absent (defaults to 0)|`{}`|
|||A2: Known, single immunity|`1` (Shatter)|
|||A3: Known, multiple immunities|`73` (Energy)|
|||A4: Unknown mask|`3`|
|`stats`|B) Attack structure|B1: Full `attacks -> projectiles` chain|`{"attacks": {"_order": ["a"], "a": {"projectiles": {"_order": ["p"], "p": {...}}}}}`|
|||B2: Attack with no projectiles|`{"attacks": {"_order": ["a"], "a": {}}}`|
|||B3: No attacks|`{}`|
|`code`|C) Upgrade code|C1: Purchased upgrade|`"_100"` -> `"1-0-0"`|
|||C2: Base upgrade|`"_000"` -> `"0-0-0"`|

Base case: A3, B1, C1

Feasibility notes: B2 and B3 make A irrelevant (no projectile), so they are tested once each with A at base. Real regression rows from `data.csv`: `0-0-0` (Sharp, pierce 1) and `1-0-0` (Energy, pierce 2).

## Base Choice Coverage

Base input (all-base): `code = "_100"`, `stats = {"range": 50, "attacks": {"_order": ["a"], "a": {"rate": 0.045, "projectiles": {"_order": ["p"], "p": {"damage": 1, "pierce": 2, "immuneBloonProperties": 73, "filterInvisible": True}}}}}`. This mirrors the real `1-0-0` row in `data.csv`.

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A3 | B1 | C1 | `row["path"] == "1-0-0"`, `damage_type == "Energy"`, `projectile_pierce == 2`, `can_hit_camo == False`, `can_pop_lead == False`, `can_pop_purple == False`, `can_pop_glass == False`, `can_pop_black == True`, `can_pop_white == True`, `can_pop_frozen == True` | `test_extract_row_all_base` |
| T2 | A1 | B1 | C1 | `damage_type == "Normal"`, every `can_pop_*` is `True` | `test_extract_row_immunity_absent` |
| T3 | A2 | B1 | C1 | `damage_type == "Shatter"`, `can_pop_lead == False`, every other `can_pop_*` is `True` | `test_extract_row_single_immunity` |
| T4 | A4 | B1 | C1 | `damage_type == "Unknown"`, every `can_pop_*` is `True` | `test_extract_row_unknown_mask` |
| T5 | A3 | B2 | C1 | with the attack changed to `{"rate": 0.045}` (no `projectiles` key): `projectile_pierce is None`, `projectile_damage is None`, `attack_rate == 0.045`, `damage_type == "Normal"`, every `can_pop_*` is `True`, `can_hit_camo == True` | `test_extract_row_attack_without_projectiles` |
| T6 | A3 | B3 | C1 | `attack_rate is None`, `projectile_pierce is None`, `range == 50`, `damage_type == "Normal"`, every `can_pop_*` is `True` | `test_extract_row_no_attacks` |
| T7 | A3 | B1 | C2 | `row["path"] == "0-0-0"`; every other field equals T1 | `test_extract_row_base_upgrade_code` |

For T5 and T6 the A selection stays at base, but it has no effect because no projectile exists; the case is still valid and the oracle shows that.
