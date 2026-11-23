# Income: cash from popping every bloon in a round

Rules for epic #89. `btd6/income.py` (#92) and the `income` CLI command (#93) must match this file. Tests: `tests/isp-tables/income.md`. Oracle: `tests/fixtures/wiki_round_cash.csv` (the wiki's per-round pop cash and end-of-round bonus for rounds 1-100).

Sources:
- [Cash] = https://www.bloonswiki.com/Cash ("Cash per pop", "End-of-round cash")
- [Rounds] = https://www.bloonswiki.com/List_of_rounds_in_BTD6 (columns "Base cash" and "Layers"; sections "Cash per pop" and "Spawning changes and Super Ceramic Bloons")
- [IncomeSet] = https://www.bloonswiki.com/JSON:Bloons_TD_6/Rounds/DefaultIncomeSet
- [Bloons] = the wiki Cargo `parent of` field already fetched by `fetch_bloons` (e.g. MOAB: `Ceramic Bloon ×4`)

The rules below reproduce the wiki's "Base cash" column for **all rounds 1-100 exactly** (checked while writing this file).

## 1. Cash per pop

Each layer popped gives $1 before the round multiplier [Cash], [Rounds]. Popping a bloon pops the bloon itself and then every child it releases, so the cash for fully popping one bloon is

```
pop_cash(bloon) = own_cash(bloon) + Σ child_count × pop_cash(child)
own_cash(bloon) = 1
```

Children come from the `parent of` field [Bloons]. Health does not matter: a Ceramic has 10 health but pays $1 for its own layer, so its pop cash (95) is lower than its RBE (104). Examples:

| Bloon | Children [Bloons] | Pop cash (rounds 1-80) |
|---|---|---|
| Red | none | 1 |
| Lead | Black ×2 | 23 |
| Rainbow | Zebra ×2 | 47 |
| Ceramic | Rainbow ×2 | 95 |
| MOAB | Ceramic ×4 | 381 |
| BFB | MOAB ×4 | 1525 |
| ZOMG | BFB ×4 | 6101 |
| DDT | Ceramic ×4 | 381 |
| BAD | ZOMG ×2, DDT ×3 | 13346 |

### Rounds 81 and later [Rounds]

- Non-MOAB-class bloons release **one** child (the first one listed, count 1) instead of all of them. A Zebra releases one Black.
- Ceramics become Super Ceramics: the Ceramic layer pays **$87** instead of $1.
- MOAB-class bloons are unchanged.

So from round 81 a Ceramic still pays 87 + 8 (its one-child chain Rainbow → Zebra → Black → Pink → Yellow → Green → Blue → Red) = 95, and so do MOAB-class bloons, but a lone Rainbow pays 8 and a Lead pays 7.

The database stores both values per bloon: `bloons.pop_cash` (rounds 1-80) and `bloons.pop_cash_super` (rounds 81+). They are computed by the ETL from `parent of` when bloons are loaded.

## 2. Round multiplier

Pop cash is multiplied by a factor that depends on the round [IncomeSet], [Rounds]:

| Rounds | Multiplier |
|---|---|
| 1-50 | 1 |
| 51-60 | 0.5 |
| 61-85 | 0.2 |
| 86-100 | 0.1 |
| 101-120 | 0.05 |
| 121-140 | 0.04 |
| 141+ | 0.02 (`finalMultiplier`) |

A threshold `{"threshold": T, "multiplier": M}` means "rounds up to and including T pay M"; the first threshold at or above the round wins. Rounds above the last threshold use `finalMultiplier`. These values live in the database (`income_thresholds`, `income_settings`), never in code.

## 3. End-of-round bonus

`end_bonus = 100 + round` [Cash] ("starts at $101 and increases by 1 every round"); [Rounds] shows `$101` for round 1 and `$140` for round 40. The bonus is **not** multiplied.

## 4. MOAB-class bloons

MOAB-class bloons use the same rule as other bloons: $1 for their own layer, plus their children's pop cash (§1). Their health (MOAB 200, BFB 700, ...) does not add cash. Fortified MOAB-class bloons release fortified children, which pay the same.

## 5. Fortified, camo and regrow

None of them change cash: fortified only raises health, camo and regrow change targeting and regrowth. The wiki's per-round cash matches with these flags ignored (e.g. round 17 "Regrow Yellow ×12" pays $48 = 12 × 4). Regrown layers re-popped by a slow defence would pay again; this file assumes every bloon is popped once without regrowing.

## 6. Formulas

```
round_pop_cash(r)    = multiplier(r) × Σ over groups in r of count × pop_cash_for_round(bloon, r)
pop_cash_for_round   = bloons.pop_cash if r <= 80 else bloons.pop_cash_super
round_income(r)      = round_pop_cash(r) + (100 + r)
cumulative_income(n) = Σ round_income(k) for k = 1..n
```

Starting cash ($650) is **not** included in `cumulative_income`.

Rounds below 1, and rounds above the last loaded round, raise `ValueError`. `round_multiplier` itself accepts any round ≥ 1 (it does not need round data).

## 7. Worked examples

| Round | Groups | Pop cash | Multiplier | End bonus | Total |
|---|---|---|---|---|---|
| 1 | Red ×20 | 20 × 1 = 20 | 1 | 101 | **121** |
| 40 | MOAB ×1 | 1 × 381 = 381 | 1 | 140 | **521** |
| 63 | Lead ×75, Ceramic ×40, ×40, ×42 | (75 × 23 + 122 × 95) = 13315 → × 0.2 = 2663 | 0.2 | 163 | **2826** |

Rounds 2-5 for golden tests: 35 + 102 = 137; 35 + 103 = 138; 71 + 104 = 175; 59 + 105 = 164.

Cumulative to round 40 [Rounds]: pop cash $12,036 + bonuses $4,820 = **$16,856**.

## 8. Exclusions

This is the cash from pops and round bonuses only. Not included: Banana Farms, Monkey Bank / Merchantman / Favored Trades, Monkey Village's Monkey Town / Monkey Commerce, Alchemist Lead to Gold / Rubber to Gold, Pirate Lord, Bounty Hunter, Benjamin, Geraldo items, Monkey Knowledge, difficulty modes, Double Cash, Half Cash, and any other tower or mode that adds or removes cash.