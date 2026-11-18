# Data notes

Findings from running `fetch_tower_module`, `resolve_all_codes` and `extract_row` over every upgrade of the five 1.0 candidate towers (issue #27). Wiki data as fetched on 2026-11-18; it changes, so rerun before relying on the counts.

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
| Alchemist | 2-2-0, 2-0-2, 2-3-0, 2-4-0, 2-5-0, 2-0-3, 2-0-4, 2-0-5 | none (first attack is "Acidic Mixture Dip", which has no projectiles) | Every projectile column is NULL and `damage_type` is derived from nothing; the real "Attack" splash is the second attack |
| Ninja Monkey | 0-0-3, 1-0-3, 0-0-4, 1-0-4, 0-0-5, 1-0-5 | "Flash Bomb", damage NULL, pierce 1 | Damage and pierce live on the second projectile, "Explosion" (damage 3 to 10, pierce 30) |
| Ninja Monkey | 0-1-4, 0-2-4, 0-1-5, 0-2-5 | "Explosion" | Summary is right for the Flash Bomb attack but misses the 100 or 600 damage Sticky Bomb |
| Wizard Monkey | 0-0-5, 1-0-5 | "Projectile" damage 1 | 100 damage MOAB-class attacks are secondary |
| Wizard Monkey | 0-5-0, 0-5-1, 0-5-2, 1-5-0, 5-1-0 | "Projectile" damage 1 | Another projectile deals up to 9 damage |
| Druid | 0-3-0, 1-3-0, 0-3-1, 0-3-2, 0-4-0, 1-4-0, 0-4-1, 0-4-2, 0-5-0, 1-5-0, 0-5-1, 0-5-2 | "Projectile" damage 1 to 6 | The Vine attack uses a 9999999 damage/pierce sentinel in a "Collidable" projectile |
| Druid | 5-0-0, 5-2-0, 5-0-1, 5-0-2 | "Projectile" damage 1 | Superstorm deals 100 damage (secondary) |

Codes are shown as paths (`_023` is `0-2-3`). Rows are flagged when another projectile of the same upgrade has more than five times the first projectile's damage, or the first projectile has no damage.

## Deferred to 2.0

Decision: the first-attack and first-projectile summaries are left as they are for 1.0. `extract_row` takes the first entry of each `_order` list, so when that entry is a "Splash" projectile, a damage-over-time effect or an attack with no projectile, damage, pierce and speed come out NULL (and the damage type is read from that entry too). The fix belongs with the 2.0 "stats per attack" work (an `attacks` table, see `docs/schema.md` "Known limitations"). Until then, a NULL in these columns can mean "the first entry is not the main hit", not "the tower has no such stat". Check the tower's resolved JSON before trusting it.

## Other things to know

- Sentinel values: `9999999` appears for damage and pierce on Druid (Vine, Ball Lightning, Superstorm spawners). Any ranking by damage or pierce must exclude or cap it, and the first-projectile summary does not currently include them.
- Alchemist's first attack is not always "Attack": for the eight upgrades above it is "Acidic Mixture Dip".
- Damage types are never `Unknown`, but only the first projectile's `immuneBloonProperties` is used, so the type of secondary attacks is not recorded.
