# `load_tower` in `btd6/db/loader.py` (proposed)

```python
def load_tower(connection: sqlite3.Connection, tower_name: str, resolved: dict[str, Any]) -> int
```

Writes one tower and its upgrades to a migrated database and returns the number of upgrade rows written. `resolved` is the output of `resolve_all_codes` (`{"_100": {...stats...}}`). For each entry the loader calls `extract_row`, looks the `damage_type` name up in `damage_types`, converts `can_hit_camo` to 0/1 and writes one `upgrades` row keyed by `(tower_id, path)`. The `can_pop_*` values of the row are ignored (`docs/schema.md`). Loading is idempotent, and the whole call is one transaction: a failure leaves the database as it was.

`load_tower` does not exist yet. The expected values below were confirmed against a throwaway reference implementation run on a migrated `:memory:` database (an upsert on `(tower_id, path)` inside `with connection:`), not against repository code. They must be rechecked when #24 implements it.

## Assumptions and open questions

- `towers.category` is `NOT NULL` but the proposed signature has no category. The tables assume the loader supplies `"Magic"` for `Super Monkey` by some mechanism (a constant mapping or an extra parameter). Decide before #24.
- "Rows written" is read as the number of upgrades processed (`len(resolved)`), so reloading the same data returns the same count and not `0`.
- An upgrade that is in the database but absent from a new `resolved` (upsert keeps it, rebuild deletes it) is not specified here. Decide, then add a block to B.
- Whether an empty `resolved` still creates the `towers` row is not specified; the oracle for A1 does not assert it.

## ISP

Characteristics: the size of `resolved` changes how many rows are written and whether anything is written (A). What the database holds for this tower decides between insert and update (B, C). Other towers' rows must survive and may share a `path` (D). Row values decide NULL handling and damage type lookup (E). A failing insert decides rollback (F). The returned count and the `SELECT` results are functional outcomes and are checked in the oracle.

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`resolved`|A) Size|A1: Empty|`{}`|
|||A2: One upgrade **(Base)**|`{"_100": STATS}`|
|||A3: Full tower, 64 upgrades|the 64-entry Super Monkey `resolved` (a trimmed fixture under `tests/fixtures/`, built from `data.json`)|
|`connection` (state)|B) Upgrades already stored for this tower|B1: None **(Base)**|only the seeded `damage_types`|
|||B2: Same paths, same values|`load_tower(connection, "Super Monkey", {"_100": STATS})` already called|
|||B3: Same path, different values|`1-0-0` stored with `range` 50 and `projectile_pierce` 2|
|`connection` (state)|C) Tower row|C1: Absent **(Base)**|`SELECT COUNT(*) FROM towers` is `0`|
|||C2: Present, no upgrades|`INSERT INTO towers (name, category) VALUES ('Super Monkey', 'Magic')`|
|`connection` (state)|D) Other towers|D1: None **(Base)**|only this tower|
|||D2: Another tower with the same `path`|`Wizard Monkey` with `1-0-0` and `range` 11|
|`resolved` (stats)|E) Values|E1: Normal row **(Base)**|`STATS` (below)|
|||E2: No attack, so NULL stats|`{"range": 50, "attacks": {"_order": []}}`|
|||E3: Unknown damage type|`STATS` with `"immuneBloonProperties": 3`|
|`resolved` (stats)|F) Insert failure|F1: Every insert succeeds **(Base)**|`{"_100": STATS}`|
|||F2: A later upgrade violates a `CHECK`|`{"_100": STATS, "_200": STATS with "range": -1}`|

Base case: A2, B1, C1, D1, E1, F1

`STATS` (the real `1-0-0` row of `data.csv`):

```python
STATS = {
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

Excluded or reduced combinations:

- B2 and B3 imply the tower row exists, so C2 is only combined with B1 (a tower row with no upgrades). C is not independent of B otherwise.
- A1 writes no upgrades, so B, D, E and F have nothing to act on; it is tested once.
- F2 with B1 shows an empty database after rollback. Rollback of *previous* contents needs B3, which is not a BCC test (T11).
- E2 and E3 are combined only with F1, since a failure is unrelated to the value type.
- A2 uses `Super Monkey` in every case; loading by another name is #26.

## Base Choice Coverage

| BCC Test | A | B | C | D | E | F | Oracle | Test Name |
|---|---|---|---|---|---|---|---|---|
| T1 | A2 | B1 | C1 | D1 | E1 | F1 | returns `1`; `SELECT COUNT(*) FROM towers` returns `1`; `SELECT COUNT(*) FROM upgrades` returns `1`; joining `towers` and `damage_types`, the row is `path == "1-0-0"`, `range == 50.0`, `projectile_pierce == 2.0`, `can_hit_camo == 0`, damage type name `"Energy"`, tower name `"Super Monkey"`, category `"Magic"` | `test_load_tower_all_base` |
| T2 | A1 | B1 | C1 | D1 | E1 | F1 | returns `0`; `SELECT COUNT(*) FROM upgrades` returns `0` | `test_load_tower_empty_resolved` |
| T3 | A3 | B1 | C1 | D1 | E1 | F1 | returns `64`; `SELECT COUNT(*) FROM upgrades` returns `64`; `SELECT COUNT(*) FROM towers` returns `1`; the `5-0-0` row has `range == 65.0`, `projectile_pierce == 20.0` and damage type `"Normal"` | `test_load_tower_full_tower` |
| T4 | A2 | B2 | C1 | D1 | E1 | F1 | the second identical call returns `1`; `SELECT COUNT(*) FROM upgrades` is still `1` and `SELECT COUNT(*) FROM towers` is still `1` | `test_load_tower_twice_is_idempotent` |
| T5 | A2 | B3 | C1 | D1 | E1 | F1 | reloading `1-0-0` with `range` 99 and `pierce` 7 returns `1`; `SELECT COUNT(*) FROM upgrades` is still `1`; the row has `range == 99.0` and `projectile_pierce == 7.0` | `test_load_tower_updates_changed_values` |
| T6 | A2 | B1 | C2 | D1 | E1 | F1 | returns `1`; `SELECT COUNT(*) FROM towers` is still `1` (no duplicate tower); `SELECT COUNT(*) FROM upgrades` returns `1` | `test_load_tower_existing_tower_row` |
| T7 | A2 | B1 | C1 | D2 | E1 | F1 | with `Wizard Monkey`'s `1-0-0` already stored: returns `1`; `SELECT COUNT(*) FROM upgrades` returns `2`; `SELECT t.name, u.range ... ORDER BY t.name` returns `[("Super Monkey", 50.0), ("Wizard Monkey", 11.0)]` | `test_load_tower_same_path_other_tower` |
| T8 | A2 | B1 | C1 | D1 | E2 | F1 | returns `1`; the row has `range == 50.0`, `can_hit_camo == 1`, damage type `"Normal"`, and `attack_rate`, `projectile_damage`, `projectile_pierce`, `ability_cooldown` are all NULL (`IS NULL` returns `1`, not `0`) | `test_load_tower_null_values` |
| T9 | A2 | B1 | C1 | D1 | E3 | F1 | returns `1`; the row's damage type name is `"Unknown"`; that `damage_types` row has `can_pop_lead IS NULL` | `test_load_tower_unknown_damage_type` |
| T10 | A2 | B1 | C1 | D1 | E1 | F2 | raises `sqlite3.IntegrityError` (`CHECK constraint failed: range IS NULL OR range >= 0`); `SELECT COUNT(*) FROM upgrades` returns `0` and `SELECT COUNT(*) FROM towers` returns `0` (the first upgrade and the tower row are rolled back) | `test_load_tower_failure_rolls_back` |
| T11 | A2 | B3 | C1 | D1 | E1 | F2 | not a BCC test (B and F varied together): with `1-0-0` stored at `range` 50, loading `{"_100": STATS with range 60, "_200": STATS with range -1}` raises `sqlite3.IntegrityError`; `SELECT COUNT(*) FROM upgrades` is still `1` and the stored `1-0-0` still has `range == 50.0` | `test_load_tower_failure_keeps_previous_contents` |

Hypothesis property: for any valid `resolved`, loading it twice gives the same table contents as loading it once, and the returned count equals `len(resolved)`.

---

## load_tower: effect rows

`load_tower` writes one `projectile_effects` row for each row of `extract_effect_rows` on each projectile, resolving `damage_type_id` by name (`Unknown` fallback) and replacing a tower's effects on reload (they cascade from the deleted upgrades). File: `tests/test_effect_loader.py`.

### ISP
|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`resolved` (effects on a projectile)|A) Number of damaging effects|A1: One|Glue `Damage over time`|
|||A2: None|Ninja 0-0-3 (no `effects`)|
|||A3: Several|three effects, damage 1, 2, 3|
|||A4: One damaging, one not|`Freeze` then `Damage over time`|
|`immuneBloonProperties` of the effect|B) Damage type|B1: Known|`64` (Acid)|
|||B2: Not in `DAMAGE_TYPES`|`3` (Unknown)|
|||B3: Differs from the projectile's|effect `0`, projectile `64` (Normal)|
|`this` (state: tower already loaded)|C) Previous contents|C1: Empty database|none|
|||C2: Same data|identical reload|
|||C3: Fewer effects|two effects, then one|
|||C4: No effects|one effect, then none|
|||C5: Other tower present|Ninja stored, Glue reloaded|

Base case: A1, B1, C1

### BCC
| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | one row: index 0, name `Damage over time`, damage 1, interval 2, lifespan 11, immediate 0, bonus NULL, `moab_only` 0, type `Acid` | `test_load_tower_stores_effect_row` |
| T2 | A2 | B1 | C1 | `SELECT COUNT(*) FROM projectile_effects` is `0` | `test_load_tower_without_effects_stores_none` |
| T3 | A3 | B1 | C1 | indices and damages `[(0, 1), (1, 2), (2, 3)]` | `test_load_tower_effect_order_preserved` |
| T4 | A4 | B1 | C1 | one row, index 1 | `test_load_tower_skips_non_damaging_effects` |
| T5 | A1 | B2 | C1 | type `"Unknown"` | `test_load_tower_effect_unknown_damage_type` |
| T6 | A1 | B3 | C1 | type `"Normal"` | `test_load_tower_effect_damage_type_independent_of_projectile` |
| T7 | A1 | B1 | C2 | rows identical (ignoring `id`), none duplicated | `test_reload_same_data_is_idempotent` |
| T8 | A1 | B1 | C3 | only the remaining effect, damage 9 | `test_reload_replaces_effects` |
| T9 | A1 | B1 | C4 | `[]` | `test_reload_without_effects_removes_them` |
| T10 | A1 | B1 | C5 | still one row | `test_reload_other_tower_keeps_effects` |

Extra tests: flags and bonus stored (`test_load_tower_stores_flags_and_bonus`); effects on two projectiles keep their own projectile (`test_load_tower_effect_on_each_projectile`). Hypothesis: loading twice leaves as many rows as extracted effects (`test_load_tower_effect_count_matches_extraction`).
