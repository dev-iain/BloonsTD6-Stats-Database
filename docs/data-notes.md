# Data notes

Findings from running `fetch_tower_module`, `resolve_all_codes` and `extract_row` over every upgrade of the five 1.0 candidate towers (issue #27). Wiki data as fetched on 2026-11-18; it changes, so rerun before relying on the counts.

Counts in sections dated before 2026-11-25 were measured before the crosspath `_order` merge fix (see "Crosspath `_order` merge" at the end). They miss attacks and projectiles on about 340 crosspath upgrades; that section has the current counts.

## Row counts

All five towers resolve to 64 upgrades (all `X-Y-Z` codes with tiers 0-5 and at most two non-zero tiers). `damage_type` is never `Unknown` for any tower.

## NULLs per column

Only columns with at least one NULL are listed. The other columns have none.

| Column | Super Monkey | Wizard Monkey | Ninja Monkey | Alchemist | Druid |
|---|---|---|---|---|---|
| footprint_radius | 10 | 0 | 0 | 0 | 0 |
| projectile_count | 0 | 63 | 18 | 64 | 8 |
| projectile_damage | 0 | 0 | 6 | 8 | 0 |
| projectile_pierce | 0 | 0 | 0 | 8 | 0 |
| projectile_speed | 0 | 7 | 12 | 64 | 8 |
| projectile_radius | 0 | 0 | 0 | 8 | 0 |
| projectile_lifespan | 0 | 0 | 0 | 8 | 8 |
| ability_cooldown | 39 | 54 | 54 | 54 | 54 |

`ability_cooldown` NULL means "no ability" and is expected. `projectile_count` and `projectile_speed` are missing from the wiki for most Wizard and Alchemist projectiles (the data omits them rather than storing a default).

## First-attack-only limitation

`extract_row` keeps the first attack, its first projectile and the first ability (see `docs/schema.md`, "Known limitations"). Upgrades affected, out of 64:

| Tower | More than one attack | An attack with more than one projectile | More than one ability |
|---|---|---|---|
| Super Monkey | 0 | 0 | 0 |
| Wizard Monkey | 30 | 23 | 0 |
| Ninja Monkey | 16 | 12 | 0 |
| Alchemist | 32 | 21 | 0 |
| Druid | 26 | 15 | 8 |

Super Monkey is the only tower with no loss. For the others, secondary attacks (Fireball, Wall of Fire, Shimmer, Dragon's Breath, Caltrops, Sticky Bomb, Lightning, Tornado, Superstorm, Vine, and so on) are not in the rows, and neither are extra projectiles such as Explosion or Spawning projectile.

## Upgrades where the first projectile is a poor summary

| Tower | Upgrades (codes) | First projectile | Problem |
|---|---|---|---|
| Alchemist | 2-2-0, 2-0-2, 2-3-0, 2-4-0, 2-5-0, 2-0-3, 2-0-4, 2-0-5 | Corrected 2026-11-25: "Attack" (the normal potion) | These eight used to resolve with "Acidic Mixture Dip" as the only attack, and this row said the NULLs were real. That was the `_order` merge bug: the `x-2-x`/`2-x-x` crosspath node lists only `["Acidic Mixture Dip"]` and replaced the parent's `["Attack"]`. With the fix, "Attack" comes first in all eight, and their projectile columns and DPS are no longer NULL |
| Ninja Monkey | 0-0-3, 1-0-3, 0-0-4, 1-0-4, 0-0-5, 1-0-5 | "Flash Bomb", damage NULL, pierce 1 | Damage and pierce live on the second projectile, "Explosion" (damage 3 to 10, pierce 30) |
| Ninja Monkey | 0-1-4, 0-2-4, 0-1-5, 0-2-5 | "Explosion" | Summary is right for the Flash Bomb attack but misses the 100 or 600 damage Sticky Bomb |
| Wizard Monkey | 0-0-5, 1-0-5 | "Projectile" damage 1 | The `MOAB` attack's "MOAB" (40) and "BFB" (100) undead projectiles are secondary, and are alternatives, not simultaneous (see "Attack and projectile tables") |
| Wizard Monkey | 0-5-0, 0-5-1, 0-5-2, 1-5-0, 5-1-0 | "Projectile" damage 1 | Another projectile deals up to 9 damage |
| Druid | 0-3-0, 1-3-0, 0-3-1, 0-3-2, 0-4-0, 1-4-0, 0-4-1, 0-4-2, 0-5-0, 1-5-0, 0-5-1, 0-5-2 | "Projectile" damage 1 to 6 | The Vine attack uses a 9999999 damage/pierce sentinel in a "Collidable" projectile |
| Druid | 5-0-0, 5-2-0, 5-0-1, 5-0-2 | "Projectile" damage 1 | Superstorm deals 100 damage (secondary) |

Codes are shown as paths (`_023` is `0-2-3`). Rows are flagged when another projectile of the same upgrade has more than five times the first projectile's damage, or the first projectile has no damage.

## Deferred to 2.0

Decision: the first-attack and first-projectile summaries are left as they are for 1.0. `extract_row` takes the first entry of each `_order` list, so when that entry is a "Splash" projectile, a damage-over-time effect or an attack with no projectile, damage, pierce and speed come out NULL (and the damage type is read from that entry too). The fix belongs with the 2.0 "stats per attack" work (an `attacks` table, see `docs/schema.md` "Known limitations"). Until then, a NULL in these columns can mean "the first entry is not the main hit", not "the tower has no such stat". Check the tower's resolved JSON before trusting it.

## NULLs from costs and ranking

- `towers.base_cost` is NULL until costs are loaded for that tower (`load_costs`, run by `refresh_database` after `load_tower`). While it is NULL, `total_cost` returns `None`, so every ranking metric for that tower is NULL and ranks last.
- `dps` is NULL when `attack_rate` is NULL or 0, or when `projectile_damage` is NULL. `damage_per_dollar` follows `dps`. The cause is the one described under "Deferred to 2.0": `extract_row` reads the first `_order` entry, which may not be the main attack (a "Splash" projectile, a damage-over-time effect, or an attack with no projectile), so damage and rate come out NULL rather than the tower lacking them (see the NULL counts for `projectile_damage` above).
- `pierce_damage_per_dollar` is also NULL when `projectile_pierce` is NULL, for the same first-entry reason (since the `_order` fix only Beast Handler has NULL pierce, 15 upgrades). Other metrics are unaffected by a NULL pierce.
- A NULL `projectile_count` is not a problem: ranking treats it as 1.

## Other things to know

- Sentinel values: `9999999` appears for damage and pierce on Druid (Vine, Ball Lightning, Superstorm spawners). Any ranking by damage or pierce must exclude or cap it, and the first-projectile summary does not currently include them.
- Alchemist's first attack is "Attack" in all 64 upgrades since the `_order` fix (it used to be "Acidic Mixture Dip" for eight crosspaths).
- Damage types are never `Unknown`, but only the first projectile's `immuneBloonProperties` is used, so the type of secondary attacks is not recorded.
- Paragons: the wiki's `btd6_upgrades` cargo table lists each paragon (Magus Perfectus, Ascended Shadow, Root of all Nature) as `path = -1`, `tier = 6`. Wizard Monkey, Ninja Monkey and Druid each have one; Super Monkey and Alchemist have none. `fetch_costs` skips them because they are not part of any `X-Y-Z` crosspath (tiers stop at 5) and `upgrade_costs.path_index` is limited to 1-3. Loading used to fail for those three towers with `CHECK constraint failed: path_index BETWEEN 1 AND 3`.
- Unused upgrades: the same cargo table has an `unused` flag. Wizard Monkey lists a cut upgrade, "Soulbind" (path 3, tier 5, 24000), next to the real "Prince of Darkness" (26500), so loading failed with `UNIQUE constraint failed: upgrade_costs.tower_id, upgrade_costs.path_index, upgrade_costs.tier`. `fetch_costs` fetches `unused` and skips rows where it is set. It is the only unused row across the five towers.

## Bloons and rounds (issue #88)

Checked with a real `fetch_bloons` and `fetch_roundset` on 2026-11-23: 25 Cargo bloon rows, and the default round set has 140 rounds of which rounds 1-100 are loaded (286 groups, every round non-empty). Rounds 1-100 are in the database; the wiki has more, which `extract_round_rows` ignores. Sanity checks: round 1 is 20 Red, round 40 contains a MOAB.

### Negative group start (round 86)

Round 86 group 0 is `BfbFortified` x5 with `start = -0.15` in the original `JSON:Bloons TD 6/Rounds/DefaultRoundSet`. It is the only negative start in rounds 1-100, and the only group with `start < 0`. It is a wiki value (cause of the negative offset not documented by the wiki), not an extraction bug. The wiki value is kept (not clamped). `round_groups.start` originally had `CHECK (start >= 0)`, which made a real `load` fail with `Rounds: failed: CHECK constraint failed: start >= 0`; migration `003_rounds.sql` now declares `start REAL NOT NULL` with no sign check (`duration` keeps `CHECK (duration >= 0)`). No group has `duration = 0` (shortest is 0.1 s), and no group has `count <= 0`.

### NULLs in `bloons`

Cargo returns empty strings for unset fields and `extract_bloon_row` turns them into NULL.

| Column | NULL for | Cause |
|---|---|---|
| health_fort, rbe_fort | every bloon except Lead, Ceramic, Moab, Bfb, Zomg, Ddt and Bad | the wiki only sets fortified values where Fortified exists in the game. Every round group with `is_fortified = 1` is on those bloons, which do have `health_fort`, so no group joins to a NULL fortified health. Queries should still use `COALESCE(health_fort, health)` |
| is_moab | stored as 0, not NULL | Cargo leaves it empty for non-MOAB bloons; the extractor maps empty to 0 |

`health`, `layers`, `rbe` and `speed` have no NULLs.

### Bloons never used in rounds 1-100

AuraBloon, DiamondBloon, DynamiteBloon, GlassBloon, RetributionBloon, RingleaderBloon, TestBloon and TestBloonMoab are in Cargo but in no round of the default round set. The first six are not part of the standard rounds (cause not stated in Cargo); TestBloon (999999 health) and TestBloonMoab (100000000 health) are developer test bloons. They are kept in `bloons` and have no `round_groups` rows, so rankings by bloon must not assume every bloon appears in a round. Loading is not affected.

### Names and keys

- Cargo `name` is the display name ("Aura Bloon", "BFB", "MOAB Test Bloon"); the roundset uses the `id` ("AuraBloon", "Bfb"). `extract_bloon_row` stores `id` as `bloons.name`, which is what `split_bloon_name` yields from a roundset name. Display names would not match.
- Roundset names carry modifiers as suffixes (`LeadFortified`, `CeramicCamoRegrow`); `split_bloon_name` strips `Fortified`, `Camo` and `Regrow` until none is left. No roundset name in rounds 1-100 fails to resolve to a Cargo bloon.
- Cargo field names can contain spaces; `normalize_cargo_keys` replaces them with `_`. The current bloon query returns none, so this is a guard.

## Bloon properties (issue #114)

Checked with a real `fetch_bloons` on 2026-11-23 (25 Cargo rows). Fixture: `tests/fixtures/bloons_immunity_cargo_response.json` (the 17 standard bloons, `immunity`, `child of`, `parent of` only).

### Source

Cargo `btd6_bloons.immunity` is usable but is **not a list of bloon properties**. It is free text naming the *damage types* the bloon is immune to (`[[damage type|Sharp, Shatter, Cold, Energy]]`), or, for the MOAB-class and a few special bloons, status effects (`[[Slow]], [[blowback]], [[knockback]]`). The properties are recovered by inverting `DAMAGE_TYPES`: a bloon carries property P when every damage type whose `cannot_damage` contains P appears in its `immunity` list (Lead: Shatter, Cold, Sharp and Energy are all listed; Zebra passes for both Black and White). The wiki JSON modules were not needed.

### Verified table

| Bloon | `immunity` text | Properties | Cross-check against `DAMAGE_TYPES` |
|---|---|---|---|
| Red, Blue, Green, Yellow, Pink | empty | none | no damage type is blocked |
| Black | Explosion | Black | Explosion is the only type with `Black` |
| White | Cold, Glacier, Frigid | White | exactly the types with `White` |
| Purple | Energy, Plasma, Fire, Frigid | Purple | exactly the types with `Purple` |
| Lead | Sharp, Shatter, Cold, Energy | Lead | exactly the types with `Lead` (Shatter, Cold, Sharp, Energy) |
| Zebra | Explosion, Cold, Glacier, Frigid | Black, White | union of Black and White types |
| Rainbow | empty | none | |
| Ceramic | empty | none | |
| Moab, Bfb, Zomg | empty | none | MOAB-class; `is_moab` carries the distinction |
| Ddt | Sharp, Shatter, Cold, Energy, Explosion | Lead, Black | union of Lead and Black types |
| Bad | Slow, blowback, knockback | none | status effects, no damage types |

Also in Cargo: GlassBloon lists `Energy, Plasma, Acid` (property Glass, plain text with no link); DiamondBloon and RetributionBloon list the same status effects as Bad, so no property.

### Empty values and quirks

- Empty `immunity` means "no property", not missing data: it is empty for every bloon that has none, including Rainbow and Ceramic.
- `frozen` is a state, not a bloon type. `Sharp` is the only type with `frozen`, and it is listed for Lead and Ddt (because of `Lead`), so the inversion rule would wrongly give them `frozen`. The parser must never derive `frozen`; it is 0 for all 25 rows.
- Camo and Regrow are round-group modifiers (`is_camo`, `is_regrow`), not Cargo properties. Fortified likewise.
- Status-effect text (Slow, blowback, knockback) is not a damage-type immunity; the parser must ignore it.
- The text is wiki markup with links; strip `[[...|label]]` the way `link_labels` does before splitting on commas.
- Damage-type names are the same as in `DAMAGE_TYPES`, so a parser can map them without a second table. `Normal` is never listed.

### Decision

The Cargo data works, so no fallback table in `btd6/etl/bloon_properties.py` is needed. #116 should derive the six flags from `immunity` through `DAMAGE_TYPES` (a bloon has property P when every damage type with P in `cannot_damage` is listed, for Lead, Black, White, Purple and Glass only; `frozen` stays 0), and take all flags as 0 when the text is empty or only names status effects.

### Round 63 has no camo

The epic text expected camo in round 63, but the wiki's `DefaultRoundSet` has only Lead x75 and Ceramic x40, x40, x42 there (no `Camo` suffix), so `round_threats(63).camo_share` is 0.0. Camo groups first appear elsewhere (26 of 286 groups in rounds 1-100 are camo). Cause: wiki data, not extraction; `docs/threats.md` records the values.

## Attack and projectile tables (epic #131, issues #132, #133)

Counts below come from `extract_attack_rows` over the resolved JSON fixtures in `tests/fixtures/{wizard,ninja,alchemist,druid}_resolved.json` (fetched 2026-11-23; Super Monkey has exactly one attack with one projectile in all 64 upgrades). Every NULL was traced to the JSON:

| Column | NULL when | Counts (attacks / projectiles) |
|---|---|---|
| `attacks.rate` | never in this data | 0 NULL |
| attacks with no `projectiles` rows | the wiki entry has only a `rate` | Alchemist 33 of 110 attacks (every "Acidic Mixture Dip"; Alchemist has no projectile on them), none elsewhere |
| `projectiles.damage` | the wiki omits `damage` (a damage-less Splash, Shimmer, Flash Bomb) or the value is the 9999999 sentinel | Wizard 8, Ninja 12, Alchemist 12, Druid 9 (the 9 Druid ones are the sentinel, with `unlimited_damage` = 1) |
| `projectiles.pierce` | the value is the 9999999 sentinel | Druid 18 (`unlimited_pierce` = 1); the other towers always give a pierce |
| `projectiles.count` | the wiki omits it; read as 1 | Wizard 131 of 152, Ninja 52 of 110, Alchemist 98 of 98, Druid 74 of 133 |
| `projectiles.speed` | the wiki omits it (instant splashes, area effects) | Wizard 55, Ninja 40, Alchemist 98, Druid 52 |
| `projectiles.lifespan` | the wiki omits it | Druid 31, none elsewhere |
| `projectiles.moab_bonus_damage` | the projectile has no `damageModifierForMoabs`, the common case | Wizard 139 of 152 NULL (13 have a bonus), Ninja 110 of 110, Alchemist 72 of 98 (26 have a bonus), Druid 133 of 133. Do not read as 0 damage bonus unless you mean "no bonus", which is the same thing for the sum `damage + COALESCE(bonus, 0)` |

`damage_type` is never "Unknown" for any projectile, and `moab_only` is set on 6 Ninja and 9 Alchemist projectiles only. `damage_type` and `can_hit_camo` are not NULL: an absent `immuneBloonProperties` reads as 0 (Normal) and an absent `filterInvisible` reads as camo-capable, the same defaults as `extract_row`.

### Wizard 0-0-5 (Prince of Darkness): MOAB and BFB are alternatives

The wiki page for Prince of Darkness (BTD6) says the undead MOAB and undead BFB are summoned by the graveyard count: "MOAB: graveyard count 20-2099", "BFB: graveyard count 2100-3000", and the regular undead bloon "always". Costs are 20 and 50 graveyard units. So the "MOAB" (damage 40, pierce 20) and "BFB" (damage 100, pierce 50) projectiles in the `MOAB` attack (rate 3) are mutually exclusive per summon, not fired together, and which one appears depends on a runtime counter that is not in the JSON. Summing them (46.667 damage per second from that attack) double counts. Convention for ranking: take the smaller (MOAB, 40) for plain DPS, because it is available once the graveyard holds 20; take the larger (BFB, 100) for MOAB DPS as the best case. A plain `1 / 0.275 + 2 / 1.5` of 4.9697 (ignoring both) understates the upgrade. The upgrade also adds +3 damage to all undead bloons (wiki "Buff"), which is not in the JSON.

### damageModifierForMoabs is additive

The wiki module that renders the stat tables (`Module:BTD6 stats`) prints the field as "+N" under the heading "Damage to MOAB-Class" (`insert_damage_mod` formats `"+%.4g"`), and the Arcane Spike page says "increases its damage from 3 to 6, with +10 additional MOAB-Class damage". Archmage: bolt damage 8 with "+19", Fireball 9 with "+24". The fixtures agree (Wizard 4-0-0: damage 6, modifier 10; 5-0-0: damage 8, modifier 19). So a MOAB-class hit does `damage + damageModifierForMoabs`, not `damage x modifier`.

## Dart, Boomerang, Bomb Shooter, Sniper and Ice Monkey (issue #135)

Checked with a real `fetch_tower_module` and `fetch_costs` on 2026-11-23. Wiki module names `Module:BTD6 stats/<tower>/new` all work for these five names. Each resolves to 64 upgrades, has a non-NULL `base_cost` (Dart 200, Boomerang 315, Bomb Shooter 375, Sniper 350, Ice 400) and 15 upgrade costs. Categories from Cargo: Primary for Dart, Boomerang, Bomb Shooter and Ice; Military for Sniper. `load_one_tower` now passes the Cargo category to `load_tower` (it used to default to `Magic`), and `fetch_costs` accepts `KNOWN_TOWERS` (the magic towers plus `EXTRA_TOWERS`). Fixtures: `tests/fixtures/<tower>_resolved_sample.json` (three upgrades each).

### NULL counts (out of 64)

Columns not listed have no NULLs. `ability_cooldown` NULL means no ability (expected).

| Column | Dart | Boomerang | Bomb Shooter | Sniper | Ice |
|---|---|---|---|---|---|
| projectile_count | 49 | 64 | 57 | 57 | 64 |
| projectile_damage | 0 | 0 | 50 | 0 | 6 |
| projectile_speed | 0 | 0 | 7 | 57 | 58 |
| ability_cooldown | 54 | 54 | 49 | 49 | 54 |

### Causes

- `projectile_count`: the wiki omits `count` when a projectile fires once, so NULL means 1 (ranking already treats it as 1). It is set only where an upgrade changes it (Dart 15 upgrades, Bomb Shooter 7, Sniper 7); Boomerang and Ice never set it.
- Bomb Shooter `projectile_damage` (50; 64 since the `_order` fix) and `damage_type`: the first projectile is the carrier "Projectile" (pierce 1, speed 180, no damage, no `immuneBloonProperties`); damage 1 to 2 and `immuneBloonProperties` 2 (Explosion) are on the second projectile "Explosion". Those rows therefore have NULL damage and `damage_type` Normal instead of Explosion (the "first entry is not the main hit" cause under "Deferred to 2.0").
- Bomb Shooter `projectile_speed` (7: 2-0-3, 2-0-4, 2-0-5, 2-2-0, 2-3-0, 2-4-0, 2-5-0): the carrier was dropped from `_order` by the crosspath merge bug, leaving "Explosion" first. Since the fix the carrier is first again and the count is 0.
- Sniper `projectile_speed` (57): the shot is hitscan (lifespan 0.1, radius 0), so the wiki has no speed. NULL means "instant", not missing data; ranking by speed sorts these last.
- Ice `projectile_speed` (58): the "Projectile" is a stationary freeze pulse (lifespan 0.05, radius 20) with no speed. The six rows with a speed are the Ice bomb upgrades.
- Ice `projectile_damage` (6: 0-0-3, 0-0-4, 0-0-5, 2-0-3, 2-0-4, 2-0-5; 15 since the `_order` fix, which restores "Ice bomb" on the `1-0-x` and `0-x-3+` crosspaths too): the first projectile is "Ice bomb" (pierce 1, speed 300, no damage, no damage type, so `damage_type` Normal); damage 1 is on the second projectile "Projectile". Same first-entry cause as Bomb Shooter.

### First-attack-only losses

| Tower | More than one attack | Attack with more than one projectile | More than one ability |
|---|---|---|---|
| Dart Monkey | 0 | 5 | 0 |
| Boomerang Monkey | 13 | 0 | 0 |
| Bomb Shooter | 0 | 49 | 0 |
| Sniper Monkey | 0 | 22 | 0 |
| Ice Monkey | 0 | 14 | 0 |

Bomb Shooter's second projectile carries its damage, so its first-projectile summary is the poorest of the five. No sentinel values appear: the largest damage across the five towers is 140 and the largest pierce 300.

Sorting by `ability_cooldown` wraps the column in `NULLIF(..., 0)`, so a cooldown of 0 (the Druid Passive Ability) sorts like NULL instead of as the shortest cooldown.

## All remaining towers (2026-11-25)

Checked against the wiki's `btd6_towers` Cargo table, which lists 27 towers. Thirteen more were added to `EXTRA_TOWERS`, so `KNOWN_TOWERS` now has 23: Tack Shooter, Glue Gunner, Desperado (Primary); Monkey Sub, Monkey Buccaneer, Monkey Ace, Heli Pilot, Mortar Monkey, Dartling Gunner (Military); Mermonkey (Magic); Spike Factory, Engineer Monkey, Beast Handler (Support). Every one has a `Module:BTD6 stats/<tower>/new` module, a base cost and 15 crosspath upgrade costs (paragon rows are skipped as before).

### Towers left out

| Tower | Why |
|---|---|
| Banana Farm, Monkey Village | No `Module:BTD6 stats/...` page at all (the farm makes money and the village buffs, so the wiki has no attack stats for them). Cargo has their costs and upgrades |
| Skywarden | New Magic tower. Only `Module:BTD6 stats/Skywarden` exists, and it is a Scribunto display config (`towerId`, `customModelNames`), not stats. There is no `/new` module yet |
| Monkey Academy | In `btd6_towers` with an empty cost and no rows in `btd6_upgrades` (not a playable tower) |

Rerun the check when the wiki adds modules for these towers, then add them to `EXTRA_TOWERS`.

### Beast Handler has 16 upgrades, not 64

`Module:BTD6 stats/Beast Handler/new` only holds `_000` and the 15 single-path codes, with no nested crosspaths, so `resolve_all_codes` returns 16. Its damage comes from `subtowers` (the beasts), which `extract_row` and `extract_attack_rows` do not read. That is why `attack_rate` is NULL for the 15 upgrades and the projectile columns are NULL for all 16 (`0-0-0` has an "Attack" whose "Projectile" has no damage).

### NULL projectile damage in the new towers

Traced in the resolved JSON. Most are the first-entry limitation described under "Deferred to 2.0":

| Tower | Upgrades | Cause |
|---|---|---|
| Glue Gunner | 59 of 64 | The glue "Projectile" has no `damage`. Glue's damage is a damage-over-time effect, which is not extracted |
| Mermonkey | 49 of 64 (42 before the `_order` fix) | The first projectile, "Projectile", has no damage. The hit is the second projectile, "Splash" (damage 2, pierce 3 at `0-0-0`). Tier 3+ top path adds a "Tentacle" attack (Explosion, 8 to 50 damage); `0-0-3` and up adds a damage-less "Trance attack" |
| Engineer Monkey | 0 since the `_order` fix (18 before) | Crosspaths such as `1-1-0` used to resolve with "Spawner" (sentries, no projectiles) first because the node's `_order` dropped the nail gun "Attack". "Attack" now comes first in all 64. The sentries' own damage is still not counted (see "Spawned units") |
| Dartling Gunner | 10 (`x-3-x`, `x-4-x`) | First projectile "Projectile" has no damage; the hit is the second projectile, "Explosion" |
| Monkey Buccaneer | 0 since the `_order` fix (7 before) | `3-2-0`, `4-2-0`, `5-2-0` and `0-2-2` to `0-2-5` resolved with `attacks._order` = `["Grape attack"]` only, so the main cannon was dropped. Fixed by the `_order` merge. The grape burn is a damage-over-time effect and is still not counted |
| Monkey Ace | 10 (6 before the `_order` fix: `0-0-4`, `1-0-4`, `0-2-4`, `0-0-5`, `1-0-5`, `0-2-5`) | First attack "Front attack" fires a "Bomb" with no damage (its "Explosion" has the damage). Other attacks have the damage |
| Desperado | 5 (`5-x-x`) | First projectile is "Area of effect" with no damage; "Projectile" (damage 20) follows it |
| Mortar Monkey | 5 (`x-x-4`) | First projectile is "MOAB burn projectile"; "Explosion" carries the damage, then decamo and DDT-defort projectiles |

## Crosspath `_order` merge (2026-11-25)

The wiki stores a crosspath (for example `_320`, nested under `_300`) as a diff over its parent. When the diff changes one entry of an `attacks`, `projectiles` or `effects` container, its `_order` lists only the entries it changed. `deep_merge` used to replace the parent's `_order` with that shorter list. The dropped entries stayed in the merged dict, but `extract_row` and `extract_attack_rows` walk `_order`, so they never saw them. Examples: Bomb Shooter `3-2-0` projectiles `["Projectile", "Explosion"]` became `["Projectile"]` (no damage, NULL DPS); Buccaneer `3-2-0` lost its cannon; Alchemist `2-2-0` lost "Attack"; Ice `1-1-0` lost its Freeze effect; Ninja `2-0-2` lost Caltrops.

Measured before the fix: 20 of the 23 towers had at least one dropped entry, about 340 upgrades in total (Engineer 34, Wizard 29, Ice 28, Bomb Shooter 25, Alchemist 23, Buccaneer 22, Druid 21, Mermonkey 21, and fewer on the rest). Super Monkey, Dart Monkey and Beast Handler were not affected.

Fix: `deep_merge` merges two `_order` lists as the parent's entries in order followed by the child's new entries (`merge_order` in `btd6/etl/fetch.py`). Every dropped entry checked (Alchemist "Attack", Engineer nail gun, Ninja Caltrops, Ice Freeze, Buccaneer cannon) still exists in the game at that crosspath. The wiki's own merge rule could not be found to confirm a child never removes an entry on purpose.

After reloading all 23 towers: `attacks` went from 1851 to 2065 rows and `projectiles` from 2312 to 2745. Upgrades with NULL DPS fell from 119 (Alchemist 8, Bomb Shooter 7, Buccaneer 7, Dartling 4, Desperado 1, Engineer 18, Glue 54, Mermonkey 5, Beast Handler 15) to 64: Glue Gunner 49 (damage over time is not extracted) and Beast Handler 15 (beasts are `subtowers`, not extracted).

### `upgrades` NULL counts after the fix (out of 64)

The `upgrades` columns still summarize the first attack and first projectile, so more crosspaths now show a damage-less first entry (a carrier, Flash Bomb, Ice bomb, Splash parent). Ranking DPS reads the `attacks` and `projectiles` tables and is not affected.

| Tower | projectile_count | projectile_damage | projectile_speed |
|---|---|---|---|
| Wizard Monkey | 64 | 0 | 0 |
| Ninja Monkey | 15 | 15 ("Flash Bomb" first on every `x-x-3+`) | 0 |
| Alchemist | 64 | 0 | 64 |
| Bomb Shooter | 64 | 64 (carrier first) | 0 |
| Sniper Monkey | 64 | 0 | 64 |
| Ice Monkey | 64 | 15 ("Ice bomb" first) | 49 |
| Mermonkey | 64 | 49 ("Projectile" before "Splash") | 0 |
| Monkey Ace | 10 | 10 ("Bomb" before its "Explosion") | 0 |
| Engineer Monkey | 49 | 0 | 0 |
| Monkey Buccaneer | 26 | 0 | 0 |

Druid has no NULLs in these columns any more (it had 8 count, 8 speed and 8 lifespan). Other towers are unchanged from the tables above.

### Still missing

- Damage over time: done, see "Damage over time" below.
- Spawned units (Engineer sentries, Beast Handler beasts in `subtowers`) are not extracted.

## Damage over time (2026-11-25)

Damaging `effects` are stored in `projectile_effects` (migration 007) and added to DPS (formula in `docs/ranking.md`). After a reload: 296 effects on 11 towers (Alchemist 90, Glue Gunner 43, Mortar 36, Dartling 36, Buccaneer 26, Wizard 20, Spike Factory 10, Ninja 10, Desperado 10, Boomerang 10, Tack Shooter 5). 11 are MOAB-only (5 "Damage over time", 6 Glue "Super Glue damage").

Upgrades with NULL DPS fell from 64 to 49: Glue Gunner 49 -> 34, Beast Handler 15 (unchanged, subtowers). DPS changed on 230 upgrades. Examples (plain / MOAB DPS before -> after): Glue 2-0-0 NULL -> 0.5; Glue 5-0-0 60 -> 80 / 160; Glue 0-0-5 1 / 1 -> 1 / 31 (Super Glue damage is MOAB-only); Alchemist 0-0-0 0.5 -> 1.0; Ninja 0-0-4 28.93 -> 128.93 (Sticky Bomb "Damage to target" 450); Desperado 5-0-0 66.67 -> 116.67; Mortar 2-0-2 1.5 -> 2.3; Dartling 2-0-0 5.0 -> 6.05 (Laser Shock).

### Glue Gunner's 34 NULL DPS upgrades are real

Checked against the resolved JSON: none of `0-x-x`, `1-0-x` or `1-x-0` (all 34) has a non-zero `damage` anywhere in the upgrade, in projectiles or effects. Plain glue only slows; Corrosive Glue (damage over time) starts at top path tier 2.

