# Ranking: damage per second and damage per dollar

Formulas for epic #94 ("best bang for buck"). `btd6/costs.py` (#97) and `btd6/ranking.py` (#98) must match this file. Tests: `tests/isp-tables/ranking.md`.

## Metrics

All inputs are columns of a `search_upgrades` result row (`docs/queries.md`) plus the upgrade's total cost.

| Metric | Formula | `metric=` value | CLI `--metric` |
|---|---|---|---|
| DPS | sum over attacks of `Σ(damage × COALESCE(count, 1)) / rate` (see below) | `"dps"` | `dps` |
| MOAB DPS | same sum with MOAB hit damage and `moab_only` projectiles included | `"moab_dps"` | |
| Pierce-weighted DPS | `DPS × projectile_pierce` | (column only) | |
| Damage per dollar | `DPS / total_cost` | `"damage_per_dollar"` (default) | `dollar` |
| Pierce damage per dollar | `pierce-weighted DPS / total_cost` | `"pierce_damage_per_dollar"` | `pierce-dollar` |

- `attack_rate` is seconds between attacks, so dividing by it gives attacks per second.
- Pierce-weighted DPS is the damage dealt when every projectile hits its full pierce of bloons. It is an upper bound: it assumes enough bloons are in the way.

## Per-attack DPS

Computed by `upgrade_dps`, `upgrade_moab_dps` and `all_upgrade_dps` in `btd6/ranking.py` from the `attacks` and `projectiles` tables (definitions in `docs/schema.md`), not from the first-projectile columns of `upgrades`.

- Attack DPS = `Σ(damage × COALESCE(count, 1)) / rate`. NULL damage counts as 0; `unlimited_damage` projectiles are excluded; attacks with NULL or 0 `rate` or no usable projectile are skipped. Upgrade DPS is the sum of attack DPS, NULL when every attack is NULL (Alchemist 2-2-0).
- `moab_only` projectiles are excluded from DPS and included in MOAB DPS. MOAB hit = `damage + COALESCE(moab_bonus_damage, 0)`.
- When one attack lists projectiles named after bloon classes (`MOAB`, `BFB`), they are alternatives: DPS takes the smallest, MOAB DPS the largest (Wizard 0-0-5: 18.3030 and 38.3030).
- Damage over time (`projectile_effects`, migration 007) is added per attack. For each effect on a projectile of an attack with rate `R`:
  - `ticks = floor(lifespan / tick_interval) + trigger_immediate` (the wiki pads lifespans, such as 11 for interval 2, so flooring gives the intended tick count).
  - effect DPS = `min(COALESCE(count, 1) × damage × ticks / R, damage / tick_interval)`. The first term is damage applied per second; the cap is what one bloon can take, because re-applying an effect refreshes it rather than stacking. This keeps effect DPS per target, like projectile DPS.
  - MOAB effect DPS uses `damage + COALESCE(moab_bonus_damage, 0)` in both places; `moab_only` effects count only toward MOAB DPS.
  - Effects count even when the projectile's own damage is NULL or unlimited. An attack whose only damage is an effect is usable (Glue Gunner 2-0-0: R = 1, damage 1, interval 2, lifespan 11, so ticks = 5 and DPS = `min(5, 0.5)` = 0.5). An effect with 0 ticks adds 0.0.

## `projectile_speed`, `range` and `projectile_lifespan`

They are shown in results but are **not part of any metric**, and they are not tie-breakers.

Rationale: how much they matter depends on the map, placement and the bloons on screen, none of which the database knows. A slow projectile still deals its full damage if it reaches the bloon, and more range only helps if bloons are inside it. Turning them into a factor would be a guess that looks precise. Users can filter on them instead (`min_range`, `min_projectile_speed`).

## NULL and zero handling

A metric is `NULL` when it cannot be computed; `NULL` metrics rank last.

| Input | Effect |
|---|---|
| every attack without usable damage or with NULL/`0` rate | DPS and everything after it NULL |
| `count` NULL | treated as `1` (the wiki omits it for single-projectile attacks; see `docs/data-notes.md`) |
| `projectile_pierce` NULL | pierce-weighted metrics NULL; plain DPS still computed |
| `total_cost` NULL (costs not loaded) or `0` | per-dollar metrics NULL |

## Total cost

`total_cost` of `X-Y-Z` = base tower cost + costs of path 1 tiers `1..X` + path 2 tiers `1..Y` + path 3 tiers `1..Z`.

- Valid paths: each tier `0..5`, at most two non-zero paths, at most one of them above tier 2 (so `3-3-0` and `1-1-1` are invalid).
- Wiki costs are Medium. Other difficulties multiply **each price separately** and round it, as `Module:BTD6 costs` (`RoundCost`) does, then add them up:
  `price(cost, m) = 5 × (round_half_up((cost / 5 − 1) × m) + 1)`, with `m` = easy `0.85`, medium `1.0`, hard `1.08`, impoppable `1.2`.
- Rounding each price, then summing, can differ by a few dollars from rounding the total. Per-price rounding matches what the game charges.

Super Monkey costs (wiki, 2026-11-23): base **2500**. Path 1: 2000, 2500, 20000, 100000, 500000. Path 2: 1500, 1900, 7500, 25000, 70000. Path 3: 3000, 1200, 5600, 55555, 165650.

## Worked examples (Super Monkey, medium)

One per damage type in the Super Monkey data. Values rounded for display; tests compare with a tolerance.

| Upgrade | Type | damage | count | rate | pierce | DPS | Pierce DPS | Cost | Damage/$ | Pierce damage/$ |
|---|---|---|---|---|---|---|---|---|---|---|
| `0-0-0` | Sharp | 1 | 1 | 0.045 | 1 | 22.2222 | 22.2222 | 2500 | 0.00888889 | 0.00888889 |
| `1-0-0` | Energy | 1 | 1 | 0.045 | 2 | 22.2222 | 44.4444 | 4500 | 0.00493827 | 0.00987654 |
| `3-0-0` | Plasma | 1 | 3 | 0.03 | 6 | 100 | 600 | 27000 | 0.00370370 | 0.02222222 |
| `0-0-4` | Normal | 2 | 1 | 0.0225 | 8 | 88.8889 | 711.111 | 67855 | 0.00130998 | 0.01047986 |

For example, `3-0-0`: DPS = 1 × 3 / 0.03 = 100; cost = 2500 + 2000 + 2500 + 20000 = 27000; damage per dollar = 100 / 27000 ≈ 0.0037037.

Difficulty, same upgrades:

| Upgrade | Easy | Medium | Hard | Impoppable |
|---|---|---|---|---|
| `0-0-0` | 2125 | 2500 | 2700 | 3000 |
| `1-0-0` | 3825 | 4500 | 4860 | 5400 |
| `0-0-4` | 57680 | 67855 | 73285 | 81425 |

## Limitations

- DPS ignores pierce and armour layers. Damage over time is included (above), but not its ceramic and lead modifiers or its `layers` limit.
- Abilities, buffs to other towers, spawned units (Engineer sentries, Beast Handler beasts), and bonus damage to specific bloon types other than MOAB-class are not included.
- Pierce-weighted metrics assume every projectile uses its full pierce.

## Ranking order

`rank_upgrades` sorts by the chosen metric, highest first; ties go to the lower total cost, then the path string; `NULL` metrics come last.
