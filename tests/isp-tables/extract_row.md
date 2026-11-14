# `extract_row(code: str, stats: dict[str, Any]) -> dict[str, Any]` in `btd6/etl/extract.py`

```python
def extract_row(code: str, stats: dict[str, Any]) -> dict[str, Any]
```

Flattens one resolved wiki upgrade into one row of 19 columns. It reads only the first attack, its first projectile and the first ability (through `first_of` and the `_order` lists). `immuneBloonProperties` on the projectile is looked up in `DAMAGE_TYPES` and decides `damage_type` and every `can_pop_*` flag (an unknown mask gives `"Unknown"` and every flag `True`). `can_hit_camo` is `not filterInvisible`, with a missing key counting as `False`. The upgrade `code` becomes the dash-separated `path`. A missing attack or projectile still gives a row, with `None` for the missing values.

All expected values below were confirmed by running `extract_row`.

## ISP

The base input for every row is the T1 input at the bottom of this file. The `Value` cells show only the part of `stats` that the block changes.

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`stats` (first projectile)|A) `immuneBloonProperties`|A1: Key absent (defaults to 0)|`{"damage": 1, "pierce": 2}`|
|||A2: Known mask, single immunity|`"immuneBloonProperties": 1` (Shatter)|
|||A3: Known mask, multiple immunities **(Base)**|`"immuneBloonProperties": 73` (Energy)|
|||A4: Mask not in `DAMAGE_TYPES`|`"immuneBloonProperties": 3`|
|`stats`|B) Attack structure|B1: First attack has a projectile **(Base)**|`{"attacks": {"_order": ["a"], "a": {"rate": 0.045, "projectiles": {"_order": ["p"], "p": {...}}}}}`|
|||B2: First attack has no projectiles|`{"attacks": {"_order": ["a"], "a": {"rate": 0.045}}}`|
|||B3: No `attacks` key|`{"range": 50}`|
|||B4: `attacks` with an empty `_order`|`{"attacks": {"_order": []}}`|
|`code`|C) Upgrade code|C1: Purchased upgrade **(Base)**|`"_100"`|
|||C2: Base upgrade, all zeros|`"_000"`|
|||C3: Crosspath with several non-zero digits|`"_023"`|
|`stats` (first projectile)|D) `filterInvisible`|D1: `True` **(Base)**|`"filterInvisible": True`|
|||D2: `False`|`"filterInvisible": False`|
|||D3: Key absent|(key omitted)|
|`stats`|E) Entries beyond the first|E1: Exactly one attack and one projectile **(Base)**|`"_order": ["a"]`, `"_order": ["p"]`|
|||E2: Two attacks, the first with two projectiles|`"_order": ["a", "b"]`, `"_order": ["p", "q"]`|
|`stats`|F) Abilities|F1: No `abilities` key **(Base)**|(key omitted)|
|||F2: First ability has a cooldown|`{"abilities": {"_order": ["x"], "x": {"cooldown": 30}}}`|

Base case: A3, B1, C1, D1, E1, F1

Excluded or reduced combinations:

- B2, B3 and B4 leave no projectile, so A, D and E have no effect there. Each is tested once with those characteristics at base.
- E2 only matters when a projectile exists (B1).
- F is read independently of the attacks, so F2 is also checked under B3 (T14, an extra non-BCC test, since the ability must be read even with no attack).
- `immuneBloonProperties` is not partitioned further: the mask values 0, 1, 73 and 3 are enough to cover the table lookup (miss, single, multiple, unknown). The `can_pop_*` flags and `damage_type` are functional outcomes of A, so they are checked in the oracle and not modeled as a characteristic.
- `range` and the other stat fields are plain `get` copies with no branching, so they are not modeled; the oracles spot-check them.

## Base Choice Coverage

Base input (T1):

```python
code = "_100"
stats = {
    "range": 50,
    "attacks": {
        "_order": ["a"],
        "a": {
            "rate": 0.045,
            "projectiles": {
                "_order": ["p"],
                "p": {
                    "damage": 1,
                    "pierce": 2,
                    "immuneBloonProperties": 73,
                    "filterInvisible": True,
                },
            },
        },
    },
}
```

This mirrors the real `1-0-0` row in `data.csv`. "Every `can_pop_*`" means the six columns `can_pop_lead`, `can_pop_black`, `can_pop_white`, `can_pop_purple`, `can_pop_glass` and `can_pop_frozen`.

| BCC Test | A | B | C | D | E | F | Oracle | Test Name |
|---|---|---|---|---|---|---|---|---|
| T1 | A3 | B1 | C1 | D1 | E1 | F1 | `row["path"] == "1-0-0"`, `range == 50`, `attack_rate == 0.045`, `projectile_damage == 1`, `projectile_pierce == 2`, `damage_type == "Energy"`, `can_hit_camo is False`, `can_pop_lead is False`, `can_pop_purple is False`, `can_pop_glass is False`, `can_pop_black is True`, `can_pop_white is True`, `can_pop_frozen is True`, `ability_cooldown is None`, `footprint_radius is None`; the row has 19 keys | `test_extract_row_all_base` |
| T2 | A1 | B1 | C1 | D1 | E1 | F1 | with `immuneBloonProperties` removed: `damage_type == "Normal"`, every `can_pop_*` is `True` | `test_extract_row_immunity_absent` |
| T3 | A2 | B1 | C1 | D1 | E1 | F1 | with mask `1`: `damage_type == "Shatter"`, `can_pop_lead is False`, every other `can_pop_*` is `True` | `test_extract_row_single_immunity` |
| T4 | A4 | B1 | C1 | D1 | E1 | F1 | with mask `3`: `damage_type == "Unknown"`, every `can_pop_*` is `True`, no exception | `test_extract_row_unknown_mask` |
| T5 | A3 | B2 | C1 | D1 | E1 | F1 | with the attack changed to `{"rate": 0.045}`: `attack_rate == 0.045`, `projectile_pierce is None`, `projectile_damage is None`, `damage_type == "Normal"`, every `can_pop_*` is `True`, `can_hit_camo is True` | `test_extract_row_attack_without_projectiles` |
| T6 | A3 | B3 | C1 | D1 | E1 | F1 | with `attacks` removed: `range == 50`, `attack_rate is None`, `projectile_pierce is None`, `damage_type == "Normal"`, every `can_pop_*` is `True`, `can_hit_camo is True` | `test_extract_row_no_attacks` |
| T7 | A3 | B4 | C1 | D1 | E1 | F1 | with `attacks = {"_order": []}`: `attack_rate is None`, `projectile_pierce is None`, `can_hit_camo is True`, no exception | `test_extract_row_empty_attack_order` |
| T8 | A3 | B1 | C2 | D1 | E1 | F1 | `row["path"] == "0-0-0"`; every other field equals T1 | `test_extract_row_base_upgrade_code` |
| T9 | A3 | B1 | C3 | D1 | E1 | F1 | `row["path"] == "0-2-3"`; every other field equals T1 | `test_extract_row_multi_digit_code` |
| T10 | A3 | B1 | C1 | D2 | E1 | F1 | `can_hit_camo is True`; every other field equals T1 | `test_extract_row_filter_invisible_false` |
| T11 | A3 | B1 | C1 | D3 | E1 | F1 | with `filterInvisible` removed: `can_hit_camo is True`; every other field equals T1 | `test_extract_row_filter_invisible_absent` |
| T12 | A3 | B1 | C1 | D1 | E2 | F1 | with a second attack `{"rate": 5}` and a second projectile `{"pierce": 9}`: `attack_rate == 0.045`, `projectile_pierce == 2`; the row equals T1 | `test_extract_row_only_first_entries_read` |
| T13 | A3 | B1 | C1 | D1 | E1 | F2 | with an ability cooldown of 30: `ability_cooldown == 30`; every other field equals T1 | `test_extract_row_ability_cooldown` |
| T14 | A3 | B3 | C1 | D1 | E1 | F2 | not a BCC test (B and F varied together): with `attacks` removed and an ability cooldown of 30, `ability_cooldown == 30` and `attack_rate is None` | `test_extract_row_ability_without_attacks` |

Regression: `data.csv` holds the real rows for all 64 Super Monkey upgrades (for example `0-0-0` is Sharp with pierce 1 and `1-0-0` is Energy with pierce 2), and `build_dataframe` over the resolved data must reproduce it. That golden test sits outside this table.
