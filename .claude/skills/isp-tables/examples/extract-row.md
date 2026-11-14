# Example: `extract_row(code: str, stats: dict) -> dict`

Take the function `extract_row(code, stats)` in `btd6/etl/extract.py`, whose ISP is provided below. First, we use interface-based modeling; we know that the function takes in the parameters `code` and `stats`, thus we model the different characteristics of each. To determine important characteristics, we first fixate on the function of the code: the caller wants one flat row describing an upgrade, including which bloon types its first projectile can pop. We know that the `immuneBloonProperties` bitmask on the projectile directly decides the `damage_type` and every `can_pop_*` flag, thus we first have to model the `immuneBloonProperties` characteristic of `stats` because it directly influences the functionality. We are also told that camo detection is read from a different field (`filterInvisible`), and that it must not change the damage type or the `can_pop_*` flags, thus we also model this characteristic to ensure the two do not influence each other. Next, we know that the function walks `attacks -> projectiles` through `_order` lists with `first_of`, so we must model the structure of `stats`: an upgrade with no attacks at all (or an empty `_order`) must still return a row instead of raising. Finally, we are interested in the interaction between the bitmask and the output flags, not the bitmask on its own; so, we create a characteristic that models which bloon properties the resolved `damage_type` says the projectile cannot pop, and check that the row reports exactly that set. For `code`, the only behavior is conversion to a path (`_023` becomes `0-2-3`), so we model only whether the code has leading underscore digits in the expected form.

## ISP

| Parameter | Characteristic | Partition | Value |
|---|---|---|---|
| `stats` (projectile) | A) `immuneBloonProperties` | A1: Key absent (defaults to 0) | `{}` |
||| A2: Known, single immunity | `1` (Shatter) |
||| A3: Known, multiple immunities (Base) | `73` (Energy) |
||| A4: Unknown mask | `3` |
| `stats` (projectile) | B) `filterInvisible` | B1: Absent | `{}` |
||| B2: True (Base) | `True` |
||| B3: False | `False` |
| `stats` | C) Attack structure | C1: Full `attacks -> projectiles` chain (Base) | `{"attacks": {"_order": ["a"], "a": {"projectiles": {"_order": ["p"], "p": {...}}}}}` |
||| C2: Attack with no projectiles | `{"attacks": {"_order": ["a"], "a": {}}}` |
||| C3: No attacks | `{}` |
| `stats` & row | D) `can_pop_*` flags vs resolved damage type | D1: Row flags equal the damage type's cannot-pop set | mask `17` (Sharp): `can_pop_lead == False`, `can_pop_frozen == False`, all others `True` |
||| D2: Unknown type pops everything | mask `3`: `damage_type == "Unknown"`, all `can_pop_*` `True` |
| `code` | E) Format | E1: Underscore + 3 digits (Base) | `"_100"` -> `"1-0-0"` |
||| E2: Base upgrade | `"_000"` -> `"0-0-0"` |

Feasibility notes: B and A are independent, so all A x B combinations are feasible and at least one pair per value is enough (all-pairs), but A1/A4 must each be tested with B2 to show camo does not change `damage_type`. C2 and C3 make A and B irrelevant (no projectile), so they are tested once each. Real regression rows from `data.csv`: `0-0-0` (Sharp, pierce 1) and `1-0-0` (Energy, pierce 2).

## Base Choice Coverage

Characteristic D is not a free choice: its blocks are determined by A (D2 is the same input as A4, and D1 is checked by the expected flags of every known mask), so D is not varied independently. It is verified through the `Expected result` of the A cases instead. BCC is therefore taken over A, B, C and E.

Base input (all-base): `code = "_100"`, `stats = {"range": 50, "attacks": {"_order": ["a"], "a": {"rate": 0.045, "projectiles": {"_order": ["p"], "p": {"damage": 1, "pierce": 2, "immuneBloonProperties": 73, "filterInvisible": True}}}}}`. This mirrors the real `1-0-0` row in `data.csv`.

| Case ID | A selection | B selection | C selection | E selection | Changed characteristic | Expected result |
| ------- | ----------- | ----------- | ----------- | ----------- | ---------------------- | --------------- |
| BCC-1 | A3 | B2 | C1 | E1 | None — All Base | `row["path"] == "1-0-0"`, `damage_type == "Energy"`, `projectile_pierce == 2`, `can_hit_camo == False`, `can_pop_lead == False`, `can_pop_purple == False`, `can_pop_glass == False`, `can_pop_black == True`, `can_pop_white == True`, `can_pop_frozen == True` |
| BCC-2 | A1 | B2 | C1 | E1 | A | `damage_type == "Normal"`, every `can_pop_*` is `True`, `can_hit_camo == False` |
| BCC-3 | A2 | B2 | C1 | E1 | A | `damage_type == "Shatter"`, `can_pop_lead == False`, every other `can_pop_*` is `True` |
| BCC-4 | A4 | B2 | C1 | E1 | A | `damage_type == "Unknown"`, every `can_pop_*` is `True` |
| BCC-5 | A3 | B1 | C1 | E1 | B | `can_hit_camo == True`, `damage_type == "Energy"` (unchanged from BCC-1) |
| BCC-6 | A3 | B3 | C1 | E1 | B | `can_hit_camo == True`, `damage_type == "Energy"` (unchanged from BCC-1) |
| BCC-7 | A3 | B2 | C2 | E1 | C with the attack changed to `{"rate": 0.045}` (no `projectiles` key): `projectile_pierce is None`, `projectile_damage is None`, `attack_rate == 0.045`, `damage_type == "Normal"`, every `can_pop_*` is `True`, `can_hit_camo == True` |
| BCC-8 | A3 | B2 | C3 | E1 | C | `attack_rate is None`, `projectile_pierce is None`, `range == 50`, `damage_type == "Normal"`, every `can_pop_*` is `True` |
| BCC-9 | A3 | B2 | C1 | E2 | E | `row["path"] == "0-0-0"`; every other field equals BCC-1 |

For BCC-7 and BCC-8 the A and B selections stay at base, but they have no effect because no projectile exists; the case is still valid and the expected result shows that.
