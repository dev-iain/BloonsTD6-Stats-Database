# `search_upgrades(connection, filters: UpgradeFilters | None = None, sort_by: str | None = None, descending: bool = True, limit: int | None = None) -> list[sqlite3.Row]`

Signature and rules from `docs/queries.md` (#31, #33). Filters left as `None` add no restriction; given filters combine with AND. `min_pierce` uses `>=` and never matches `NULL`. A negative threshold, a `sort_by` outside the whitelist, and `limit < 1` each raise `ValueError`. Results are always ordered: by `sort_by` when given (`NULL` last), with ties and unsorted results ordered by tower name, then path.

This table covers the characteristics named in #32 (pierce threshold, lead flag, filter combination, empty table, `NULL` values) plus the `filters`, `sort_by` and `limit` parameters, since #33 and #37 build on the same signature. The other numeric thresholds (#35), the other `can_pop_*` flags (#34), `damage_type` and `can_hit_camo` (#36), and `tower_name` and `category` (#38) are not partitioned here; their characteristics get added to this file when those issues are worked on.

Test fixture: in-memory SQLite DB with the schema from `docs/queries.md`, seeded with four real Super Monkey rows from `data.csv`. Expected results are written as lists of paths in the returned order; every listed path is a Super Monkey upgrade unless marked otherwise.

| tower | path | projectile_pierce | can_pop_lead | damage_type |
|---|---|---|---|---|
| Super Monkey | `0-0-0` | 1 | False | Sharp |
| Super Monkey | `1-1-0` | 3 | False | Energy |
| Super Monkey | `2-0-0` | 2 | True | Plasma |
| Super Monkey | `2-1-0` | 3 | True | Plasma |

`NULL` row (only in E2): Alchemist `0-0-1`, `projectile_pierce = NULL`, `can_pop_lead = False`, `damage_type = Sharp`. Alchemist data is not loaded yet, so this row is inserted by hand, modeled on the Alchemist upgrades that have `NULL` pierce.

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

Feasibility notes: use an in-memory SQLite DB, never a mock. D2 makes A, B, H and E irrelevant, so it is tested once. `data.csv` has no `NULL` pierce, so E2 needs the row inserted by hand. "Rows exist but none match" is not a separate block: it is the result of A3 against this fixture. C2 makes A, B and H irrelevant, since there is no filters object to read.

## Base Choice Coverage

H is not varied independently: it is decided by which of A and B is `None`. H1 (Base) is the all-base case, H2 is covered by A4 and B3, and H3 needs two changes at once, so it is an extra non-BCC test. I only matters when F is F2: changing I alone from the F1 base would not change the result, so I1 (Base) holds in every BCC case and I2 is covered by an extra test. BCC is therefore taken over A, B, C, D, E, F and G.

The base for A is `0` rather than `3` so that E2 is meaningful: with `min_pierce=0`, an implementation that treats `NULL` as `0` would wrongly include the Alchemist row. The base for B is `False` so that the base result has two rows in a known order, which makes the G2 and F2 cases show a real change.

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

BCC-4 returns the same list as BCC-1 because every stored pierce is at least 1. It is still required, since it proves that `None` adds no restriction where `0` would.

## Extra non-BCC tests

| Case ID | Covers | Expected result |
|---|---|---|
| EXTRA-1 | H3 | `search_upgrades(conn, UpgradeFilters())` returns `["0-0-0", "1-1-0", "2-0-0", "2-1-0"]` |
| EXTRA-2 | I1, tie-break, `NULL` last | with E2, `search_upgrades(conn, sort_by="projectile_pierce")` returns `["1-1-0", "2-1-0", "2-0-0", "0-0-0", Alchemist "0-0-1"]` |
| EXTRA-3 | I2, `NULL` last | with E2, `search_upgrades(conn, sort_by="projectile_pierce", descending=False)` returns `["0-0-0", "2-0-0", "1-1-0", "2-1-0", Alchemist "0-0-1"]` |
| EXTRA-4 | #37 acceptance | `search_upgrades(conn, sort_by="projectile_pierce", limit=2)` returns `["1-1-0", "2-1-0"]` |
