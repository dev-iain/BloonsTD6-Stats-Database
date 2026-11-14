# `search_upgrades(connection, filters: UpgradeFilters | None = None, sort_by: str | None = None, descending: bool = True, limit: int | None = None) -> list[sqlite3.Row]`

## Rules for these tests

- Behavior is defined in `docs/queries.md`.
- `conn` is an in-memory SQLite connection with the schema from `docs/queries.md`. Never mock SQLite.
- Compare `[row["path"] for row in result]` to the expected list, in order. Every path is Super Monkey unless marked Alchemist.
- Expected `ValueError` cases use `pytest.raises(ValueError)`.

Fixture rows (from `data.csv`):

| tower | path | projectile_pierce | can_pop_lead | damage_type |
|---|---|---|---|---|
| Super Monkey | `0-0-0` | 1 | False | Sharp |
| Super Monkey | `1-1-0` | 3 | False | Energy |
| Super Monkey | `2-0-0` | 2 | True | Plasma |
| Super Monkey | `2-1-0` | 3 | True | Plasma |

E2 only: add Alchemist `0-0-1`, `projectile_pierce = NULL`, `can_pop_lead = False`, `damage_type = Sharp` (inserted by hand).

## ISP

| Variable | Characteristic | Partition/Block | Representative Value |
|---|---|---|---|
| V1: `filters.min_pierce` | A: Threshold vs stored pierce values (1, 2, 3, 3) | A1 (Base): below every value | `0` |
| V1: `filters.min_pierce` | A: Threshold vs stored pierce values | A2: equal to an existing value (inclusive boundary) | `3` |
| V1: `filters.min_pierce` | A: Threshold vs stored pierce values | A3: one above the highest value | `4` |
| V1: `filters.min_pierce` | A: Threshold vs stored pierce values | A4: no filter | `None` |
| V1: `filters.min_pierce` | A: Threshold vs stored pierce values | A5: negative (invalid) | `-1` |
| V2: `filters.can_pop_lead` | B: Lead filter | B1: must pop lead | `True` |
| V2: `filters.can_pop_lead` | B: Lead filter | B2 (Base): must not pop lead | `False` |
| V2: `filters.can_pop_lead` | B: Lead filter | B3: no filter | `None` |
| V3: `filters` | C: Filters object | C1 (Base): an `UpgradeFilters` instance | `UpgradeFilters(min_pierce=..., can_pop_lead=...)` |
| V3: `filters` | C: Filters object | C2: omitted | `None` |
| V4: database | D: Table state | D1 (Base): rows exist | the four-row fixture |
| V4: database | D: Table state | D2: empty | schema only, no rows |
| V4: database | E: Pierce values stored | E1 (Base): all non-null | the four-row fixture |
| V4: database | E: Pierce values stored | E2: one `NULL` | fixture plus Alchemist `0-0-1` |
| V5: `sort_by` | F: Sort column | F1 (Base): no sort | `None` |
| V5: `sort_by` | F: Sort column | F2: whitelisted column | `"projectile_pierce"` |
| V5: `sort_by` | F: Sort column | F3: not whitelisted (hostile) | `"; DROP TABLE upgrades"` |
| V6: `limit` | G: Limit | G1 (Base): no limit | `None` |
| V6: `limit` | G: Limit | G2: smallest valid | `1` |
| V6: `limit` | G: Limit | G3: below 1 (invalid) | `0` |
| V1 + V2 | H: Filter combination | H1 (Base): both given (AND) | `min_pierce=3, can_pop_lead=False` -> `["1-1-0"]` |
| V1 + V2 | H: Filter combination | H2: only one given | `min_pierce=3, can_pop_lead=None` -> `["1-1-0", "2-1-0"]` |
| V1 + V2 | H: Filter combination | H3: neither given | `UpgradeFilters()` -> every row |
| V7: `descending` | I: Sort direction | I1 (Base): descending (the default) | `True` |
| V7: `descending` | I: Sort direction | I2: ascending | `False` |

C2 takes no filters, so A and B do not apply to it.

## Base Choice Coverage

Excluded from BCC: H is decided by which of A and B is `None` (H2 in BCC-4 and BCC-7, H3 in EXTRA-1). I has no effect unless F is F2 (I2 in EXTRA-3).

| Case ID | A | B | C | D | E | F | G | Changed characteristic | Expected result |
|---|---|---|---|---|---|---|---|---|---|
| BCC-1 | A1 | B2 | C1 | D1 | E1 | F1 | G1 | None — All Base | `search_upgrades(conn, UpgradeFilters(min_pierce=0, can_pop_lead=False))` returns `["0-0-0", "1-1-0"]` |
| BCC-2 | A2 | B2 | C1 | D1 | E1 | F1 | G1 | A | `UpgradeFilters(min_pierce=3, can_pop_lead=False)` returns `["1-1-0"]` |
| BCC-3 | A3 | B2 | C1 | D1 | E1 | F1 | G1 | A | `UpgradeFilters(min_pierce=4, can_pop_lead=False)` returns `[]` |
| BCC-4 | A4 | B2 | C1 | D1 | E1 | F1 | G1 | A | `UpgradeFilters(min_pierce=None, can_pop_lead=False)` returns `["0-0-0", "1-1-0"]` |
| BCC-5 | A5 | B2 | C1 | D1 | E1 | F1 | G1 | A | `UpgradeFilters(min_pierce=-1, can_pop_lead=False)` raises `ValueError` |
| BCC-6 | A1 | B1 | C1 | D1 | E1 | F1 | G1 | B | `UpgradeFilters(min_pierce=0, can_pop_lead=True)` returns `["2-0-0", "2-1-0"]` |
| BCC-7 | A1 | B3 | C1 | D1 | E1 | F1 | G1 | B | `UpgradeFilters(min_pierce=0, can_pop_lead=None)` returns `["0-0-0", "1-1-0", "2-0-0", "2-1-0"]` |
| BCC-8 | — | — | C2 | D1 | E1 | F1 | G1 | C | `search_upgrades(conn)` returns `["0-0-0", "1-1-0", "2-0-0", "2-1-0"]` |
| BCC-9 | A1 | B2 | C1 | D2 | E1 | F1 | G1 | D | on the empty table, `UpgradeFilters(min_pierce=0, can_pop_lead=False)` returns `[]` |
| BCC-10 | A1 | B2 | C1 | D1 | E2 | F1 | G1 | E | with Alchemist `0-0-1` inserted, `UpgradeFilters(min_pierce=0, can_pop_lead=False)` returns `["0-0-0", "1-1-0"]`; Alchemist `0-0-1` is absent |
| BCC-11 | A1 | B2 | C1 | D1 | E1 | F2 | G1 | F | base filters with `sort_by="projectile_pierce"` returns `["1-1-0", "0-0-0"]` |
| BCC-12 | A1 | B2 | C1 | D1 | E1 | F3 | G1 | F | base filters with `sort_by="; DROP TABLE upgrades"` raises `ValueError`; afterward `SELECT COUNT(*) FROM upgrades` returns `4` |
| BCC-13 | A1 | B2 | C1 | D1 | E1 | F1 | G2 | G | base filters with `limit=1` returns `["0-0-0"]` |
| BCC-14 | A1 | B2 | C1 | D1 | E1 | F1 | G3 | G | base filters with `limit=0` raises `ValueError` |

## Extra non-BCC tests

| Case ID | Covers | Expected result |
|---|---|---|
| EXTRA-1 | H3 | `search_upgrades(conn, UpgradeFilters())` returns `["0-0-0", "1-1-0", "2-0-0", "2-1-0"]` |
| EXTRA-2 | I1, tie-break, `NULL` last | with E2, `search_upgrades(conn, sort_by="projectile_pierce")` returns `["1-1-0", "2-1-0", "2-0-0", "0-0-0", Alchemist "0-0-1"]` |
| EXTRA-3 | I2, `NULL` last | with E2, `search_upgrades(conn, sort_by="projectile_pierce", descending=False)` returns `["0-0-0", "2-0-0", "1-1-0", "2-1-0", Alchemist "0-0-1"]` |
| EXTRA-4 | #37 acceptance | `search_upgrades(conn, sort_by="projectile_pierce", limit=2)` returns `["1-1-0", "2-1-0"]` |
