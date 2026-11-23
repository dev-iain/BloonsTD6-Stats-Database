# Ranking: damage per second and damage per dollar

Formulas for epic #94 ("best bang for buck"). `btd6/costs.py` (#97) and `btd6/ranking.py` (#98) must match this file. Tests: `tests/isp-tables/ranking.md`.

## Metrics

All inputs are columns of a `search_upgrades` result row (`docs/queries.md`) plus the upgrade's total cost.

| Metric | Formula | `metric=` value | CLI `--metric` |
|---|---|---|---|
| DPS | `projectile_damage × projectile_count / attack_rate` | `"dps"` | `dps` |
| Pierce-weighted DPS | `DPS × projectile_pierce` | (column only) | |
| Damage per dollar | `DPS / total_cost` | `"damage_per_dollar"` (default) | `dollar` |
| Pierce damage per dollar | `pierce-weighted DPS / total_cost` | `"pierce_damage_per_dollar"` | `pierce-dollar` |

- `attack_rate` is seconds between attacks, so dividing by it gives attacks per second.
- Pierce-weighted DPS is the damage dealt when every projectile hits its full pierce of bloons. It is an upper bound: it assumes enough bloons are in the way.

## `projectile_speed`, `range` and `projectile_lifespan`

They are shown in results but are **not part of any metric**, and they are not tie-breakers.

Rationale: how much they matter depends on the map, placement and the bloons on screen, none of which the database knows. A slow projectile still deals its full damage if it reaches the bloon, and more range only helps if bloons are inside it. Turning them into a factor would be a guess that looks precise. Users can filter on them instead (`min_range`, `min_projectile_speed`).

## NULL and zero handling

A metric is `NULL` when it cannot be computed; `NULL` metrics rank last.

| Input | Effect |
|---|---|
| `projectile_damage` NULL | DPS and everything after it NULL |
| `projectile_count` NULL | treated as `1` (the wiki omits it for single-projectile attacks; see `docs/data-notes.md`) |
| `attack_rate` NULL or `0` | DPS NULL (no division by zero) |
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

- `extract_row` reads only the first attack and its first projectile (`docs/data-notes.md`). For Wizard, Ninja, Alchemist and Druid, upgrades with several attacks are under-counted, so their DPS is a lower bound. Super Monkey is unaffected.
- Abilities, buffs to other towers, damage-over-time, and bonus damage to specific bloon types are not included.
- Pierce-weighted metrics assume every projectile uses its full pierce.

## Ranking order

`rank_upgrades` sorts by the chosen metric, highest first; ties go to the lower total cost, then the path string; `NULL` metrics come last.
