# Attacks and projectiles (epic #131, issue #132)

Specification for #133 (migration `006_attacks.sql`, extractor, loader) and #134 (DPS). Design and column meanings: `docs/schema.md`, "`attacks` and `projectiles`". None of the functions below exist yet; names are proposals.

Real inputs were checked against the resolved JSON fetched on 2026-11-23 (`write_resolved_json` for each tower, trimmed as `fetch.py` does today). Values marked "variant" are the real upgrade edited in one place, so a block can be changed on its own; the edit is part of the `Value` cell. The fixtures for #133 must also keep `damageModifierForMoabs` and `filterOutNonMoabs`, which `PROJECTILE_FIELDS` trims away today.

Real cases used throughout (resolved JSON, trimmed):

| Case | Attacks (rate) -> projectiles (`damage`/`pierce`/`count`) | Ability |
|---|---|---|
| Ninja 0-0-3 (`NINJA_003`) | `Attack` (0.62) -> `Flash Bomb` (-/1/-), `Explosion` (3/30/-), `Projectile` (1/4/1); `Caltrops` (3.9) -> `Projectile` (1/6/-) | none |
| Wizard 0-0-5 (`WIZARD_005`) | `Attack` (0.275) -> `Projectile` (1/8/-); `Shimmer` (1) -> `Projectile` (-/500/-); `Reanimate` (1.5) -> `Projectile` (2/1/-); `MOAB` (3) -> `MOAB` (40/20/-), `BFB` (100/50/-) | none |
| Druid 0-3-0 (`DRUID_030`) | `Attack` (1.1) -> `Projectile` (1/1/8); `Vine` (2.6) -> `Collidable` (9999999/9999999/-), `Projectile` (1/20/-) | none |
| Druid 4-0-0 (`DRUID_400`) | `Attack` (1.1) -> `Projectile` (1/2/5); `Ball Lightning` (6) -> `Spawning projectile` (0/9999999/-), `Lightning` (3/5/-); `Lightning` (2.3) -> `Lightning` (3/5/-); `Tornado` (2.5) -> `Projectile` (0/60/-) | none |
| Alchemist 2-2-0 (`ALCH_220`) | `Acidic Mixture Dip` (10) -> no projectiles (only attack) | none |
| Alchemist 0-4-0 (`ALCH_040`) | `Attack` (2) -> `Splash` (1/15/-) | `Ability` cooldown 60 |
| Druid 0-4-0 (`DRUID_040`) | same attacks as Druid 0-3-0 | `Passive Ability` cooldown 0, `Vine Crush` cooldown 30 |
| Wizard 4-0-0 (`WIZARD_400`) | `Attack` (0.275) -> `Projectile` (6/7/-, `damageModifierForMoabs` 10) | none |
| Super Monkey 0-0-0 (`SUPER_000`) | `Attack` (0.045) -> `Projectile` (1/1/1) | none |

Note that the existing `extract_row` summary (first attack, first projectile) gives: Ninja 0-0-3 `projectile_damage` NULL; Wizard 0-0-5 damage 1 only; Druid 0-3-0 damage 1, pierce 1; Alchemist 2-2-0 every projectile column NULL and `can_hit_camo` 1 (default), `damage_type` Normal.

## extract_attack_rows

```python
def extract_attack_rows(stats: dict[str, Any]) -> list[dict[str, Any]]
```

Walks `stats["attacks"]["_order"]` and each attack's `projectiles["_order"]` and returns one dict per attack, `{"attack_index", "name", "rate", "projectiles": [...]}`, where each projectile dict has `projectile_index, name, damage, pierce, unlimited_damage, unlimited_pierce, moab_bonus_damage, moab_only, count, speed, radius, lifespan, damage_type, can_hit_camo`. A damage or pierce equal to 9999999 becomes `None` with its `unlimited_*` flag `True`. A missing `attacks` key gives `[]`. The `extract_row` summary is not changed.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`stats`|A) Number of attacks|A1: None|`{"range": 50}` (no `attacks` key; synthetic, no real upgrade has none)|
|||A2: One|`ALCH_220` (one attack)|
|||A3: Several **(Base)**|`NINJA_003` (2 attacks)|
|`stats`|B) Projectiles in the largest attack|B1: None|`ALCH_220` (`Acidic Mixture Dip` has no `projectiles`)|
|||B2: One|`SUPER_000`|
|||B3: Several **(Base)**|`NINJA_003` (`Attack` has 3)|
|`stats`|C) `damage` on the projectiles|C1: Every projectile has it|`WIZARD_400`|
|||C2: At least one projectile lacks it **(Base)**|`NINJA_003` (`Flash Bomb`)|
|`stats`|D) The 9999999 sentinel|D1: Absent **(Base)**|`NINJA_003`|
|||D2: On `pierce` only|`DRUID_400` (`Spawning projectile`)|
|||D3: On `damage` and `pierce`|`DRUID_030` (`Collidable`)|
|`stats`|E) MOAB damage modifier|E1: No projectile has `damageModifierForMoabs` **(Base)**|`NINJA_003`|
|||E2: A projectile has it|`WIZARD_400` (value 10)|
|`stats`|F) `moab_only` projectiles (`filterOutNonMoabs`)|F1: None **(Base)**|`NINJA_003`|
|||F2: A projectile has it|Ninja 0-0-4 `Sticky Bomb` `Projectile` (real; resolved JSON of `_004`)|

Base case: A3, B3, C2, D1, E1, F1 (`NINJA_003`).

A1 forces B1 (no attack has projectiles), so the pair is not independent; the A1 test is the extra combined test.

### BCC

Every row except T1 is `NINJA_003` with the edit shown; the real upgrades in the ISP are cross-checked in the "Real cases" table below.

| BCC Test | A | B | C | D | E | F | Input | Oracle | Test Name |
|---|---|---|---|---|---|---|---|---|---|
| T1 | A3 | B3 | C2 | D1 | E1 | F1 | `NINJA_003` | 2 attack dicts: `(0, "Attack", 0.62)` with projectiles `Flash Bomb` (damage `None`, pierce 1, speed 300, radius 5, lifespan 0.57, `damage_type` `"Normal"`, `can_hit_camo` `True`), `Explosion` (3, 30, `damage_type` `"Normal"`), `Projectile` (1, 4, count 1, `"Sharp"`); `(1, "Caltrops", 3.9)` with one `Projectile` (1, 6, lifespan 35, `"Sharp"`). Every `unlimited_*` and `moab_only` is `False`, every `moab_bonus_damage` is `None`; the indices are 0, 1, 2 and 0 | `test_extract_attack_rows_several_attacks` |
| T2 | A2 | B3 | C2 | D1 | E1 | F1 | delete `Caltrops` from `_order` | `len(rows)` is 1, `rows[0]["name"]` is `"Attack"` | `test_extract_attack_rows_one_attack` |
| T3 | A1 | B1 | C2 | D1 | E1 | F1 | `{"range": 50}` | `[]` (extra test: A1 cannot hold B3, not BCC) | `test_extract_attack_rows_no_attacks` |
| T4 | A2 | B1 | C2 | D1 | E1 | F1 | `ALCH_220` | `[{"attack_index": 0, "name": "Acidic Mixture Dip", "rate": 10, "projectiles": []}]` | `test_extract_attack_rows_attack_without_projectiles` |
| T5 | A3 | B2 | C2 | D1 | E1 | F1 | `NINJA_003` with `Explosion` and `Projectile` deleted from `Attack`'s `_order` | `rows[0]["projectiles"]` has 1 entry (`Flash Bomb`) and `rows[1]["projectiles"]` has 1 (`Caltrops`) | `test_extract_attack_rows_one_projectile_each` |
| T6 | A3 | B3 | C1 | D1 | E1 | F1 | `Flash Bomb` gets `damage` 2 | every projectile `damage` is a number: `[2, 3, 1, 1]` | `test_extract_attack_rows_all_damage_present` |
| T7 | A3 | B3 | C2 | D2 | E1 | F1 | `Caltrops` `Projectile` gets `pierce` 9999999 | that projectile: `pierce` is `None`, `unlimited_pierce` is `True`, `damage` is 1, `unlimited_damage` is `False` | `test_extract_attack_rows_sentinel_pierce_only` |
| T8 | A3 | B3 | C2 | D3 | E1 | F1 | `Caltrops` `Projectile` gets `damage` and `pierce` 9999999 | `damage` and `pierce` are `None`, both flags `True`; `Flash Bomb` stays `damage` `None` with `unlimited_damage` `False` | `test_extract_attack_rows_sentinel_damage_and_pierce` |
| T9 | A3 | B3 | C2 | D1 | E2 | F1 | `Explosion` gets `damageModifierForMoabs` 10 | `Explosion` `moab_bonus_damage` is 10; the other projectiles `None` | `test_extract_attack_rows_moab_bonus` |
| T10 | A3 | B3 | C2 | D1 | E1 | F2 | `Caltrops` `Projectile` gets `filterOutNonMoabs` true | that projectile `moab_only` is `True`, all others `False` | `test_extract_attack_rows_moab_only` |

### Real cases (golden, against the resolved JSON)

| Upgrade | Oracle |
|---|---|
| Ninja 0-0-3 | T1 values above (the `Explosion` projectile has `damage` 3, `pierce` 30; the `extract_row` summary has damage `None`, which is the bug this fixes) |
| Wizard 0-0-5 | 4 attacks; the largest has 2 projectiles; `MOAB` projectile `MOAB` `damage` 40, `BFB` `damage` 100; `Shimmer` `Projectile` `damage` `None`, `pierce` 500 |
| Druid 0-3-0 | 2 attacks; `Collidable` `damage` `None`, `pierce` `None`, both flags `True`; `Vine` `Projectile` 1 / 20 |
| Druid 4-0-0 | `Spawning projectile` `damage` 0, `pierce` `None`, `unlimited_pierce` `True`, `unlimited_damage` `False` |
| Alchemist 2-2-0 | 1 attack (`Acidic Mixture Dip`, rate 10), 0 projectiles; the resolved JSON has no `Attack` at 2-2-0 although 2-1-0 and 3-2-0 do |

## load_tower (attack and projectile storage)

```python
def load_tower(connection: sqlite3.Connection, tower_name: str, resolved: dict[str, Any], category: str = "Magic") -> int
```

In addition to the `upgrades` rows (`docs/schema.md`, Loader), writes one `attacks` row per attack and one `projectiles` row per projectile in the same transaction, replacing the tower's earlier rows (cascade from `upgrades`). `upgrades.ability_cooldown` is the first ability's cooldown. The cases below extend `tests/isp-tables/loader.md`; they only add the characteristics that attack storage changes.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`connection` (state)|A) Rows already stored for the tower|A1: None **(Base)**|migrated, seeded database|
|||A2: Same data|`load_tower` already called with the same `resolved`|
|||A3: More attacks than the new data|`NINJA_003` stored first, then reloaded with `Caltrops` deleted|
|`resolved`|B) Abilities of the upgrade|B1: None **(Base)**|`{"_003": NINJA_003}`|
|||B2: One|variant: `NINJA_003` plus `abilities` `{"_order": ["Ability"], "Ability": {"cooldown": 60}}` (the Alchemist 0-4-0 shape)|
|||B3: Two|variant: `NINJA_003` plus Druid 0-4-0's `Passive Ability` (0) and `Vine Crush` (30)|
|`resolved`|C) 9999999 sentinel|C1: Absent **(Base)**|`NINJA_003`|
|||C2: On `pierce` only|`{"_400": DRUID_400}`|
|||C3: On `damage` and `pierce`|`{"_030": DRUID_030}`|
|`resolved`|D) An attack with no projectiles|D1: None **(Base)**|`NINJA_003`|
|||D2: One|`{"_220": ALCH_220}`|

Base case: A1, B1, C1, D1.

### BCC

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | returns 1; `SELECT COUNT(*) FROM attacks` is 2; `SELECT COUNT(*) FROM projectiles` is 4; `Attack`'s `Flash Bomb` row has `damage` NULL and `unlimited_damage` 0; `upgrades.ability_cooldown` is NULL; `upgrades.projectile_damage` is NULL (unchanged summary) | `test_load_tower_stores_attacks_and_projectiles` |
| T2 | A2 | B1 | C1 | D1 | `attacks` still has 2 rows and `projectiles` 4 (no duplicates after the reload; ids are not asserted) | `test_load_tower_reload_keeps_attack_counts` |
| T3 | A3 | B1 | C1 | D1 | after the reload `attacks` has 1 row and `projectiles` 3 (no orphan `Caltrops` rows) | `test_load_tower_reload_removes_stale_attacks` |
| T4 | A1 | B2 | C1 | D1 | `upgrades.ability_cooldown` is 60.0 | `test_load_tower_one_ability` |
| T5 | A1 | B3 | C1 | D1 | `upgrades.ability_cooldown` is 0.0 (the first ability, passive; NULL would mean "no ability") | `test_load_tower_two_abilities_keeps_first` |
| T6 | A1 | B1 | C2 | D1 | the `Spawning projectile` row has `damage` 0.0, `pierce` NULL, `unlimited_pierce` 1, `unlimited_damage` 0 | `test_load_tower_sentinel_pierce_only` |
| T7 | A1 | B1 | C3 | D1 | the `Collidable` row has `damage` NULL, `pierce` NULL, both flags 1; no row contains 9999999 | `test_load_tower_sentinel_damage_and_pierce` |
| T8 | A1 | B1 | C1 | D2 | returns 1; `attacks` has 1 row (`Acidic Mixture Dip`, `rate` 10.0), `projectiles` has 0 rows; `upgrades.projectile_damage` is NULL | `test_load_tower_attack_without_projectiles` |

Extra checks that are not BCC (one characteristic each, so they are not new tests of a block):

- No projectile column holds 9999999 after loading the Druid data (`SELECT COUNT(*) FROM projectiles WHERE damage = 9999999 OR pierce = 9999999` is 0).
- `INSERT` of a `projectiles` row with `unlimited_damage` 1 and a non-NULL `damage` raises `sqlite3.IntegrityError` (the `CHECK`).
- Deleting an upgrade deletes its `attacks` and `projectiles` rows (cascade), with foreign keys on.
- `EXPLAIN QUERY PLAN` for `WHERE upgrade_id = ?` on `attacks` and `WHERE attack_id = ?` on `projectiles` names `sqlite_autoindex_attacks_1` and `sqlite_autoindex_projectiles_1` (no extra index was created).
- `INSERT` of a `projectiles` row with `unlimited_pierce` 1 and a non-NULL `pierce` raises `sqlite3.IntegrityError`.
- Deleting an `attacks` row deletes its `projectiles` rows (cascade).
- `extract_row` and `extract_attack_rows` agree on the sentinel: a first projectile with `damage` or `pierce` 9999999 gives NULL in the `upgrades` column too (synthetic variant of `DRUID_030` with `Collidable` first).
- `upgrades.ability_cooldown` for Druid 0-4-0 is 0.0 (passive first); the cooldown sort and filter treat 0 as "no active ability" (`NULLIF(ability_cooldown, 0)`), tested in `test_search`.
- Consistency (all 64 upgrades of each tower, no exclusions): `upgrades.attack_rate` equals the `rate` of `attack_index` 0 and `upgrades.projectile_damage` equals `damage` of `projectile_index` 0 of that attack.

## upgrade_dps and upgrade_moab_dps

```python
def upgrade_dps(connection: sqlite3.Connection, upgrade_id: int) -> float | None
def upgrade_moab_dps(connection: sqlite3.Connection, upgrade_id: int) -> float | None
def all_upgrade_dps(connection: sqlite3.Connection) -> dict[int, tuple[float | None, float | None]]
```

`all_upgrade_dps` computes both figures for every upgrade in one pass (for ranking, avoiding one query per upgrade); its result must equal the per-upgrade functions for every id (tested on the Ninja, Wizard, Druid and Alchemist data).

Sums per-attack DPS over all attacks of the upgrade, as defined in `docs/schema.md` ("DPS definitions"): `damage x COALESCE(count, 1)` per projectile (NULL damage counts 0, unlimited damage is excluded), divided by `rate`; an attack with a NULL or 0 rate, or with no projectile that has numeric damage, is skipped; `None` when nothing is left. `upgrade_moab_dps` uses `damage + COALESCE(moab_bonus_damage, 0)` and includes `moab_only` projectiles, which `upgrade_dps` leaves out.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`upgrade_id`|A) Attacks that contribute|A1: None|variant: `NINJA_003` with `_order` of `attacks` emptied (no attacks stored)|
|||A2: One|variant: `NINJA_003` without `Caltrops`|
|||A3: Several **(Base)**|`NINJA_003`|
|`upgrade_id`|B) `rate` of the attack|B1: Positive **(Base)**|`Caltrops` rate 3.9|
|||B2: NULL|variant: `Caltrops` without `rate`|
|||B3: 0|variant: `Caltrops` `rate` 0|
|`upgrade_id`|C) Damage of the projectiles in an attack|C1: Every projectile has a number|variant: `Flash Bomb` gets `damage` 2|
|||C2: Some NULL, some numeric **(Base)**|`NINJA_003` `Attack`|
|||C3: None numeric (no projectile or all NULL)|variant: `Attack`'s three projectiles have no `damage`|
|`upgrade_id`|D) Unlimited damage|D1: None **(Base)**|`NINJA_003`|
|||D2: A projectile has `unlimited_damage` 1|variant: `Caltrops` `Projectile` `damage` 9999999|
|`upgrade_id`|E) `count` of a projectile|E1: NULL (read as 1) **(Base)**|`Explosion` count absent|
|||E2: Greater than 1|variant: `Explosion` `count` 2|
|`upgrade_id`|F) MOAB bonus|F1: None **(Base)**|`NINJA_003`|
|||F2: Present|variant: `Explosion` `damageModifierForMoabs` 10|
|`upgrade_id`|G) `moab_only` projectiles|G1: None **(Base)**|`NINJA_003`|
|||G2: Present|variant: `Caltrops` `Projectile` `filterOutNonMoabs` true|

Base case: A3, B1, C2, D1, E1, F1, G1.

### BCC

Oracle is `(upgrade_dps, upgrade_moab_dps)`, compared with `pytest.approx`. The base is `(4 / 0.62) + (1 / 3.9)` for both.

| BCC Test | A | B | C | D | E | F | G | Oracle | Test Name |
|---|---|---|---|---|---|---|---|---|---|
| T1 | A3 | B1 | C2 | D1 | E1 | F1 | G1 | `(6.70802, 6.70802)` | `test_upgrade_dps_ninja_0_0_3` |
| T2 | A1 | B1 | C2 | D1 | E1 | F1 | G1 | `(None, None)` | `test_upgrade_dps_no_attacks_is_none` |
| T3 | A2 | B1 | C2 | D1 | E1 | F1 | G1 | `(6.45161, 6.45161)` (`4 / 0.62`) | `test_upgrade_dps_one_attack` |
| T4 | A3 | B2 | C2 | D1 | E1 | F1 | G1 | `(6.45161, 6.45161)` (`Caltrops` skipped) | `test_upgrade_dps_null_rate_skips_attack` |
| T5 | A3 | B3 | C2 | D1 | E1 | F1 | G1 | `(6.45161, 6.45161)` and no `ZeroDivisionError` | `test_upgrade_dps_zero_rate_skips_attack` |
| T6 | A3 | B1 | C1 | D1 | E1 | F1 | G1 | `(9.93383, 9.93383)` (`6 / 0.62 + 1 / 3.9`) | `test_upgrade_dps_all_damage_present` |
| T7 | A3 | B1 | C3 | D1 | E1 | F1 | G1 | `(0.25641, 0.25641)` (`Attack` skipped, `Caltrops` only) | `test_upgrade_dps_attack_without_damage_skipped` |
| T8 | A3 | B1 | C2 | D2 | E1 | F1 | G1 | `(6.45161, 6.45161)`; `Caltrops` excluded, not infinite | `test_upgrade_dps_unlimited_damage_excluded` |
| T9 | A3 | B1 | C2 | D1 | E2 | F1 | G1 | `(11.54673, 11.54673)` (`7 / 0.62 + 1 / 3.9`) | `test_upgrade_dps_count_multiplies` |
| T10 | A3 | B1 | C2 | D1 | E1 | F2 | G1 | `(6.70802, 22.83706)` (`14 / 0.62 + 1 / 3.9`) | `test_upgrade_moab_dps_bonus` |
| T11 | A3 | B1 | C2 | D1 | E1 | F1 | G2 | `(6.45161, 6.70802)` (`moab_only` only in MOAB DPS) | `test_upgrade_dps_moab_only_split` |

### Real cases (golden)

| Upgrade | `upgrade_dps` | `upgrade_moab_dps` | Notes |
|---|---|---|---|
| Ninja 0-0-3 | 6.70802 | 6.70802 | `(3 + 1) / 0.62 + 1 / 3.9`; the `extract_row` summary gives NULL |
| Wizard 0-0-5 | 18.30303 | 38.30303 | Confirmed on the wiki (#133): `MOAB` (40) and `BFB` (100) are per-summon alternatives by graveyard count. Plain DPS `1 / 0.275 + 2 / 1.5 + 40 / 3`, MOAB DPS with the larger, `100 / 3`; `Shimmer` skipped (no damage). The old simultaneous sum was 51.63636 |
| Druid 0-3-0 | 7.65734 | 7.65734 | `8 / 1.1 + 1 / 2.6`; `Collidable` excluded; `has_unlimited_damage` true |
| Druid 4-0-0 | 6.34980 | 6.34980 | `5 / 1.1 + 3 / 6 + 3 / 2.3`; `Spawning projectile` damage 0 and `Tornado` damage 0 add nothing; pierce is unlimited but not used by DPS |
| Alchemist 2-2-0 | `None` | `None` | one attack, no projectile |
| Wizard 4-0-0 | 21.81818 | 58.18182 | `6 / 0.275` and `(6 + 10) / 0.275` |
| Super Monkey 0-0-0 | 22.22222 | 22.22222 | `1 / 0.045`; matches the existing `docs/ranking.md` example |

---

## extract_effect_rows (damage over time)

```python
def extract_effect_rows(effects: dict[str, Any]) -> list[dict[str, Any]]
```

Walks `effects["_order"]` and returns one dict per effect with a numeric `damage` > 0 and numeric `interval` > 0: `effect_index` (position in `_order`, skipped entries still count), `name`, `damage`, `tick_interval`, `lifespan` (0 when absent), `trigger_immediate`, `moab_bonus_damage`, `moab_only`, `damage_type` (from the effect's own `immuneBloonProperties`). `extract_projectile_row` adds `"effects"` holding this list (`[]` when the projectile has no `effects`). File: `tests/test_extract_effect_rows.py`.

### ISP
|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`effects`|A) Container|A1: One effect|Glue 2-0-0 `Damage over time` (damage 1, interval 2, lifespan 11)|
|||A2: Missing or empty `_order`|`{}` and `{"_order": []}`|
|||A3: Several effects, some skipped|`Freeze`, damage 0, `Laser Shock`, `Super Glue damage`|
|`damage`|B) Value|B1: Positive number|`1`|
|||B2: Absent (e.g. `Freeze`)|no key|
|||B3: Zero, negative or not a number|`0`, `-3`, `"lots"`|
|`interval`|C) Value|C1: Positive number|`2`|
|||C2: Zero or negative|`0`, `-1`|
|||C3: Absent|no key|
|`lifespan`|D) Presence|D1: Present|`11`|
|||D2: Absent|no key|
|`triggerImmediate`|E) Value|E1: `false`|`False`|
|||E2: `true`|`True`|
|||E3: Absent|no key|
|`damageModifierForMoabs`|F) Presence|F1: Absent|no key|
|||F2: Present|`3`|
|`filterOutNonMoabs`|G) Value|G1: Absent or `false`|no key|
|||G2: `true`|`True`|
|`immuneBloonProperties`|H) Mask|H1: Known, non-zero|`64` (Acid)|
|||H2: Zero|`0` (Normal)|
|||H3: Absent|no key (Normal)|
|||H4: Not in `DAMAGE_TYPES`|`3` (Unknown)|

Base case: A1, B1, C1, D1, E1, F1, G1, H1

### BCC
| BCC Test | A | B | C | D | E | F | G | H | Oracle | Test Name |
|---|---|---|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | F1 | G1 | H1 | one row: index 0, damage 1, `tick_interval` 2, lifespan 11, immediate `False`, bonus `None`, `moab_only` `False`, `"Acid"` | `test_extract_effect_rows_all_base` |
| T2 | A2 | B1 | C1 | D1 | E1 | F1 | G1 | H1 | `[]` (both inputs) | `test_extract_effect_rows_empty_container` |
| T3 | A3 | B1 | C1 | D1 | E1 | F1 | G1 | H1 | rows indexed `2` and `3` only | `test_extract_effect_rows_index_is_position_in_order` |
| T4 | A1 | B2 | C1 | D1 | E1 | F1 | G1 | H1 | `[]` | `test_extract_effect_rows_skips_effect_without_damage` |
| T5 | A1 | B3 | C1 | D1 | E1 | F1 | G1 | H1 | `[]` for each value | `test_extract_effect_rows_skips_unusable_numbers` |
| T6 | A1 | B1 | C2 | D1 | E1 | F1 | G1 | H1 | `[]` | `test_extract_effect_rows_skips_unusable_numbers` |
| T7 | A1 | B1 | C3 | D1 | E1 | F1 | G1 | H1 | `[]` | `test_extract_effect_rows_skips_missing_interval` |
| T8 | A1 | B1 | C1 | D2 | E1 | F1 | G1 | H1 | `lifespan == 0` | `test_extract_effect_rows_missing_lifespan_is_zero` |
| T9 | A1 | B1 | C1 | D1 | E2 | F1 | G1 | H1 | `trigger_immediate is True` | `test_extract_effect_rows_trigger_immediate_true` |
| T10 | A1 | B1 | C1 | D1 | E3 | F1 | G1 | H1 | `trigger_immediate is False` | `test_extract_effect_rows_missing_trigger_immediate_is_false` |
| T11 | A1 | B1 | C1 | D1 | E1 | F2 | G1 | H1 | `moab_bonus_damage == 3` | `test_extract_effect_rows_moab_bonus` |
| T12 | A1 | B1 | C1 | D1 | E1 | F1 | G2 | H1 | `moab_only is True` | `test_extract_effect_rows_moab_only` |
| T13 | A1 | B1 | C1 | D1 | E1 | F1 | G1 | H2 | `damage_type == "Normal"` | `test_extract_effect_rows_damage_type_from_own_mask` |
| T14 | A1 | B1 | C1 | D1 | E1 | F1 | G1 | H3 | `damage_type == "Normal"` | `test_extract_effect_rows_missing_mask_is_normal` |
| T15 | A1 | B1 | C1 | D1 | E1 | F1 | G1 | H4 | `damage_type == "Unknown"` | `test_extract_effect_rows_damage_type_from_own_mask` |

Extra tests (not BCC): `extract_projectile_row` has `"effects"` (list, `[]` when absent or `{}`): `test_projectile_row_has_effects_key`, `test_projectile_row_without_effects_is_empty_list`; `extract_attack_rows` nests them per projectile: `test_attack_rows_carry_effects_per_projectile`; Ninja 0-0-4 shape (450, 2.95, 3): `test_extract_effect_rows_ninja_damage_to_target`. Hypothesis: for any list of effects the returned indices are strictly increasing and within `_order`, and every row has `damage > 0`, `tick_interval > 0`, `lifespan >= 0` (`test_extract_effect_rows_only_positive_numbers_and_ordered`).

---

## projectile_effects table (migration 007)

`007_projectile_effects.sql`; file `tests/test_effects_migration.py`. Columns, CHECKs, `UNIQUE (projectile_id, effect_index)`, `ON DELETE CASCADE` from projectile, attack, upgrade and tower, `PRAGMA user_version` 7, and applying to a version 6 database runs only `007`. Index plans in `tests/test_db_indexes.py` (`sqlite_autoindex_projectile_effects_1` for effects of a projectile, `idx_projectile_effects_damage_type_id`). Boundaries: `damage` 0 rejected / 0.5 accepted; `tick_interval` 0 rejected / 0.01 accepted; `lifespan` 0 accepted / -0.1 rejected; `moab_bonus_damage` NULL and 0 accepted / -1 rejected; flags 0 and 1 accepted / 2 rejected.
