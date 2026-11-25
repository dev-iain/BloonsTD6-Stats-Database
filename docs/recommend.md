# Recommender: lookahead round-fit score and affordability

`btd6/recommend.py`: `recommend(connection, round_number, money, difficulty="medium", limit=None, horizon=DEFAULT_HORIZON, owned=None, one_per_tower=False) -> list[Recommendation]` (epic #119). It returns the upgrades you can afford now that can pop everything the current round contains, ranked by how well they fit the current round **and the next few rounds**. The rules are deterministic: no randomness, no LLM. Tests: `tests/isp-tables/recommend.md`.

Inputs come from two existing modules:

- `round_threats` (`btd6/threats.py`, `docs/threats.md`): `camo_share`, `property_share[prop]`, `moab_share`, `crowd_density`.
- `rank_upgrades` (`btd6/ranking.py`, `docs/ranking.md`): `total_cost`, `dps`, `moab_dps`, `pierce_weighted_dps`, `projectile_pierce`, `range`, `can_hit_camo`, `can_pop_*`.

## Constants

| Name | Value | Reason |
|---|---|---|
| `MIN_PROPERTY_SHARE` | `0.05` | A property that makes up less than 5% of the round's RBE can be handled by a second tower, so it should not remove every other upgrade from the list. Round 63's lead share (0.1197) is above the threshold. |
| `HIGH_PIERCE` | `5` | Smallest **effective** pierce labelled `high_pierce`. Base Dart Monkey has pierce 2 and base Super Monkey 1, while crowd-clearing tiers start around 5 (Super Monkey `3-0-0` has 6). |
| `DEFAULT_HORIZON` | `5` | Rounds scored, counting the current one. Five rounds is long enough to see the first camo (round 24) or lead (round 28) coming, so you can buy for it ahead of time. |
| `HORIZON_DECAY` | `0.75` | Weight of round `N + k` is `0.75 ** k`. The current round matters most, and round `N + 4` still counts about a third as much. |

## Window

The window is the loaded rounds `r` with `round_number <= r <= round_number + horizon - 1`, in order. It always holds `round_number`. Near the last loaded round it is shorter. `horizon = 1` scores only the current round.

## Eligibility

An upgrade is a candidate only if all of these hold **for the current round**:

1. `total_cost` is not NULL and `total_cost <= money`. A NULL cost (costs not loaded) is never affordable. Money is what you have now: projected income is not added.
2. If `camo_share > 0`: `can_hit_camo` is true. Any camo at all is a leak, so camo is a hard filter.
3. For every property with `property_share[prop] >= MIN_PROPERTY_SHARE`: `can_pop_<prop>` is true.

Rules 2 and 3 go into an `UpgradeFilters` (`filters_for_threats`), so the filtering happens in SQL through `search_upgrades`. Rule 1 is applied to the `rank_upgrades` frame.

### Needs and leaks in later rounds

A round's **needs** are `camo` (when `camo_share > 0`) followed by each property required by rule 3, in `PROPERTY_NAMES` order. `unmet_needs(row, threats) -> tuple[str, ...]` returns the needs the upgrade does not meet (`can_hit_camo` / `can_pop_<prop>` false), in that order. A candidate **leaks** at a later window round when that round has an unmet need. Leaking does not remove a candidate. It zeroes that round's fit and pushes the candidate below every candidate that does not leak (see Ordering).

## Owned towers

`owned: Sequence[OwnedTower] | None`. `OwnedTower` is a `NamedTuple` of `tower_name: str` and `path: str` (`X-Y-Z`), defined in `btd6/recommend.py` so the recommender does not depend on `btd6.game_state`. `None` and `()` behave the same.

- **Validation:** an entry whose `path` is not `X-Y-Z` with digits 0-5 raises `QueryError` (`owned path must be X-Y-Z, got '1-2'`). An entry whose `(tower_name, path)` has no row in `upgrades` (a tower outside the database, or an impossible crosspath) is **ignored**, because the live game can report towers the database does not have.
- **Coverage:** a need (`camo` or a property) is **covered** when at least one known owned tower meets it (`can_hit_camo`, `can_pop_<prop>`). Covered needs are dropped everywhere: from the current round's filters (`filters_for_threats(threats, covered)`), from `unmet_needs` in later window rounds, and from the `hits_camo` / `pops_<prop>` reason codes. Example: owning Ninja Monkey `0-0-0` covers `camo`, so in round 24 a Dart Monkey `0-0-0` is eligible and does not get `fails_camo_at_24`.
- **Upgrade candidates:** for each distinct known owned `(tower_name, path)` P, every upgrade Q of the same tower with each tier of Q at least the tier of P, and Q ≠ P, is a candidate. Its price is `cost(Q) − cost(P)` (both from `total_cost` at `difficulty`). It must pass the same eligibility as a new purchase, with the price in place of the cost. If P or Q has no cost, Q is skipped.
- **Upgrade score:** the value of an upgrade in one round is the extra damage it adds:

```
value(row, t)  = 0.0 if unmet_needs(row, t) else moab_term + pierce_term     (the round_score numerator)
upgrade_fit_k  = (value(Q, t_k) − value(P, t_k)) / price
score          = Σ w_k × upgrade_fit_k / Σ w_k
```

  A NULL value for Q or P in any window round makes the score NULL. The score can be negative, for example when Q loses pierce in a crowded round, and it sorts by value like any other score.
- New purchases are still offered for towers you own. A second Ninja Monkey is a separate tower.

## One per tower

`one_per_tower=True` keeps only the first result for each `tower_name` after sorting and before `limit`. A new purchase and an upgrade of an owned tower of the same name count as the same tower. With `limit=5` you get the best five different towers.

## Effective pierce

The old pierce term `dps × projectile_pierce` assumed every point of pierce lands on every attack. A tower only hits the bloons inside its range, so pierce is capped by how many bloons are in range at the same time:

```
crowd            = crowd_density × 2 × range            (bloons inside a range circle's diameter of track)
effective_pierce = min(projectile_pierce, max(1, crowd))
```

`effective_pierce(pierce, range, density) -> float | None`:

- `pierce` NULL or NaN gives `None`.
- `range` NULL/NaN, or `density` `None`, gives `pierce` (no cap).
- The `max(1, …)` floor means a tower with pierce at least 1 always hits at least one bloon.

Example: round 1 has `crowd_density` 0.0457. Ice Monkey `0-0-0` (range 20, pierce 40) gets `min(40, 1.83) = 1.83`. Ninja Monkey `0-0-0` (range 40, pierce 2) gets `min(2, 3.66) = 2`.

## Score

For one round with threats `t` and `m = t.moab_share`:

```
moab_term   = m × moab_dps
pierce_term = (1 − m) × dps × effective_pierce(projectile_pierce, range, t.crowd_density)
round_fit   = (moab_term + pierce_term) / total_cost        (round_score)
```

`round_fit` is `0.0` for a window round where the candidate has an unmet need.

Over the window rounds `r_0 = round_number, r_1, …` with weights `w_k = HORIZON_DECAY ** (r_k − round_number)`:

```
score = Σ w_k × round_fit_k / Σ w_k
```

- MOABs have one hit target and many layers, so they need single-target damage (`moab_dps`, which includes MOAB bonus damage and `moab_only` projectiles). Everything else comes in crowds, so pierce counts, up to the crowd size.
- Dividing by `total_cost` makes it "fit per dollar", like `damage_per_dollar`.

### NULL handling

- A term whose weight is `0` is left out. If `m = 0`, a NULL `moab_dps` does not matter. If `m = 1`, a NULL `projectile_pierce` or `dps` does not matter.
- If a term with a non-zero weight is NULL, that round's fit is NULL. A round zeroed by an unmet need is `0.0`, never NULL.
- If any window round's fit is NULL, the score is NULL.
- `total_cost` of `0` gives a NULL score. NULL costs are already filtered out by eligibility.
- NULL scores rank last within their leak group. They are still returned, because the upgrade is affordable and can pop the current round.

## Ordering

1. Candidates that do not leak in the window come first (`first_leak_round` is `None`).
2. Then highest score first, with NULL scores last.
3. Ties go to the lower `total_cost`, then `tower_name`, then `path`, then new purchases before upgrades.

`limit` is applied after sorting.

## `Recommendation`

Frozen dataclass:

| Field | Type | Source |
|---|---|---|
| `tower_name` | `str` | `search_upgrades` |
| `path` | `str` | `X-Y-Z` |
| `total_cost` | `int` | what you pay now: `total_cost` at `difficulty` for a new purchase, the price `cost(Q) − cost(P)` for an upgrade |
| `upgrade_from` | `str \| None` | the owned path P for an upgrade, `None` for a new purchase (field placed after `total_cost`) |
| `score` | `float \| None` | window score above |
| `dps` | `float \| None` | `add_metrics` |
| `moab_dps` | `float \| None` | `add_metrics` |
| `pierce_weighted_dps` | `float \| None` | `add_metrics` (uncapped, `dps × projectile_pierce`) |
| `projectile_pierce` | `float \| None` | `search_upgrades` |
| `effective_pierce` | `float \| None` | `effective_pierce` for the **current** round |
| `first_leak_round` | `int \| None` | first window round with an unmet need, `None` if none |
| `reasons` | `tuple[str, ...]` | reason codes, in the order listed below |

### Reason codes

| Code | When |
|---|---|
| `affordable` | always (every result passed rule 1) |
| `upgrades_owned` | the result is an upgrade of an owned tower (comes right after `affordable`) |
| `hits_camo` | the current round has camo (`camo_share > 0`) and camo is not covered by an owned tower |
| `pops_<prop>` | for each property required by rule 3 in the current round and not covered, in `PROPERTY_NAMES` order (`pops_lead`, `pops_black`, …) |
| `high_pierce` | current round: `pierce_term > moab_term` and `effective_pierce >= HIGH_PIERCE` |
| `high_single_target` | current round: `moab_term > pierce_term` |
| `fails_<need>_at_<round>` | for each need that is unmet in some later window round, at the **first** such round (`fails_camo_at_24`, `fails_lead_at_28`). Sorted by round, then by need order (`camo` first, then `PROPERTY_NAMES`). |

A NULL term counts as `0` when the terms are compared. At most one of `high_pierce` and `high_single_target` is given.

## Errors

| Input | Error | Message |
|---|---|---|
| `money` not an `int`, or a `bool` | `QueryError` | `money must be a whole number, got '5000'` (`{money!r}`) |
| `money < 0` | `QueryError` | `money must be 0 or more, got -1` |
| `difficulty` not easy/medium/hard/impoppable | `QueryError` | from `validate_difficulty` |
| `limit` not an `int` (or a `bool`) | `QueryError` | `limit must be a whole number, got '3'` |
| `limit < 1` | `QueryError` | `limit must be at least 1, got 0` (same as `rank_upgrades`) |
| `horizon` not an `int` (or a `bool`) | `QueryError` | `horizon must be a whole number, got '5'` |
| `horizon < 1` | `QueryError` | `horizon must be at least 1, got 0` |
| an `owned` path that is not `X-Y-Z` (0-5) | `QueryError` | `owned path must be X-Y-Z, got '1-2'` |
| `one_per_tower` not a `bool` | `QueryError` | `one_per_tower must be true or false, got 'yes'` |
| `round_number` not an `int`, or outside the loaded rounds | `QueryError` | the `validate_round` message, e.g. `Round 150 is not loaded; loaded rounds are 1-100` |
| no rounds loaded | `NoRoundDataError` | `No round data loaded` |

Validation order: `money`, `difficulty`, `limit`, `horizon`, `owned`, `one_per_tower`, then the round.

`money = 0`, or costs not loaded, gives `[]`. These are not errors.

## Callers

- CLI: `python -m btd6 recommend --round N --money X [--horizon H] [--one-per-tower]`. With `--live`, the known towers in the game state are passed as `owned`, and a line `Owned: Ninja Monkey 0-0-0, Dart Monkey 2-0-0` (or `Owned: none`) is printed under the live line. The table has a `leaks at` column (blank when `first_leak_round` is `None`) and an `upgrade from` column after `path` (blank for new purchases).
- API: `GET /api/recommendations?...&horizon=H&one_per_tower=true&owned=Ninja Monkey 0-0-0&owned=...`. `horizon` is optional (default `DEFAULT_HORIZON`). `one_per_tower` accepts `true`/`false`/`1`/`0`/`on` (case-insensitive) and is false when absent or blank. Any other value is a 422 `one_per_tower must be true or false, got 'yes'`. `owned` is repeated, each value `<tower name> <X-Y-Z>`. A value without a trailing `X-Y-Z` is a 422 `owned must be '<tower name> X-Y-Z', got 'Ninja'`. Invalid values give the same 422 as other bad params. Each record includes every `Recommendation` field.
- Web UI (Recommend tab): a **One per tower** checkbox (`name="one_per_tower"`, value `true`) and an **Upgrade from** column. While **Use live game** is ticked and the state is fresh, the request carries one `owned` param per known tower from `GET /api/game-state`, and the status line reads `Counting N owned towers.`
- Agent tool `recommend`: optional `horizon` (integer, minimum 1), `one_per_tower` (boolean) and `owned` (array of strings `<tower name> <X-Y-Z>`), passed through. Parsing `owned` strings uses the same rule as the API.

## Worked examples (Super Monkey, medium, data from `docs/ranking.md`)

| Upgrade | Type | pops lead | camo | DPS = MOAB DPS | pierce | pierce DPS | cost |
|---|---|---|---|---|---|---|---|
| `0-0-0` | Sharp | no | no | 22.2222 | 1 | 22.2222 | 2500 |
| `1-0-0` | Energy | no | no | 22.2222 | 2 | 44.4444 | 4500 |
| `3-0-0` | Plasma | yes | no | 100 | 6 | 600 | 27000 |
| `0-0-4` | Normal | yes | yes | 88.8889 | 8 | 711.111 | 67855 |

Real round data (wiki, 2026-11-23) with `money = 100000` and `horizon = 1`, from `btd6.db` on 2026-11-24. Round `crowd_density`: round 1 0.045682, round 40 0.04, round 63 0.581598. The `0-0-4` MOAB DPS in the current data is higher than the table above (it includes MOAB bonus damage), so its round 40 score is `222.22 / 67855`.

**Round 40** (`moab_share` 1.0, no properties, no camo). All four are eligible. `score = moab_dps / cost`, and pierce plays no part:

| Rank | Upgrade | score | reasons |
|---|---|---|---|
| 1 | `0-0-0` | 0.00888889 | `affordable`, `high_single_target` |
| 2 | `1-0-0` | 0.00493827 | `affordable`, `high_single_target` |
| 3 | `3-0-0` | 0.00370370 | `affordable`, `high_single_target` |
| 4 | `0-0-4` | 0.00327496 | `affordable`, `high_single_target` |

**Round 63** (`moab_share` 0, lead 0.1197 ≥ 0.05, no camo). Only lead poppers are eligible. The round is dense, so the cap does not bind (effective pierce = pierce):

| Rank | Upgrade | effective pierce | score | reasons |
|---|---|---|---|---|
| 1 | `3-0-0` | 6 | 0.0222222 | `affordable`, `pops_lead`, `high_pierce` |
| 2 | `0-0-4` | 8 | 0.0104799 | `affordable`, `pops_lead`, `high_pierce` |

**Round 1** (20 Red over 17.5 s, `moab_share` 0, nothing required). The bloons are sparse, so the cap binds for `3-0-0` and `0-0-4`:

| Rank | Upgrade | effective pierce | score | reasons |
|---|---|---|---|---|
| 1 | `3-0-0` | 4.568 (pierce 6) | 0.0169191 | `affordable` |
| 2 | `1-0-0` | 2 | 0.00987654 | `affordable` |
| 3 | `0-0-0` | 1 | 0.00888889 | `affordable` |
| 4 | `0-0-4` | 5.208 (pierce 8) | 0.00682201 | `affordable`, `high_pierce` |

Pierce against single-target: `1-0-0` (pierce 2) ranks above `0-0-0` (pierce 1) in round 1, and below it in round 40. The two have the same DPS.

### Full database (default horizon 5)

| Round, money | Top pick | Why |
|---|---|---|
| 1, 650 | Druid `0-0-0` | Ice Monkey `0-0-0` (pierce 40, range 20) gets effective pierce 1.83 and drops out of the top 5; before the cap it ranked first. |
| 20, 650 | Ninja Monkey `0-0-0` | Round 24 has a camo group. Every pick that cannot hit camo leaks at 24 (`fails_camo_at_24`) and sorts after Ninja. Before the lookahead, Ice Monkey `0-0-0` ranked first. |
| 40, 5000 | Dart Monkey `2-0-4` | single target |
| 63, 5000 | Ninja Monkey `0-1-3` | pops lead, high pierce |

## Limitations

- Round 63 has no camo in the wiki's `DefaultRoundSet` (`docs/threats.md`), so its results are not required to hit camo, even though the roadmap mentions camo.
- Ceramic adds no property. Its weight comes in through the RBE-weighted pierce term, not through a filter.
- Stats are per upgrade. Owned towers are used for coverage and upgrades only. The recommender does not consider buffs, abilities or placement, or whether an owned tower has enough damage for the needs it covers. A Ninja Monkey `0-0-0` covers camo even at round 80.
- Money is what you have now. Income earned during the window is not added, so it does not plan "buy now, upgrade before round R".
- `crowd_density` uses each group's spawn rate and speed. It ignores track length, bloon children spawned on pop, and overlapping groups.
