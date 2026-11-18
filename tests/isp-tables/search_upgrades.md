# `search_upgrades(connection, filters: UpgradeFilters | None = None, sort_by: str | None = None, descending: bool = True, limit: int | None = None) -> list[sqlite3.Row]`

Returns the upgrades that satisfy every filter in `filters`, ordered by `sort_by` and cut to `limit` rows. A filter left as `None` restricts nothing.

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

Take the function `search_upgrades`. First, we use interface-based modeling; we know that the function takes in a filters object, a sort column, a direction and a limit, thus we model the characteristics of each. To determine important characteristics, we first fixate on the function of the code: the caller wants only the upgrades that satisfy every filter they gave, and a filter left as `None` must not restrict anything. We know that `min_pierce` is compared against the `projectile_pierce` column, thus we model its position relative to the stored values, with boundary values on both sides of a real value, because off-by-one errors (`>` versus `>=`) are the most likely bug, plus a negative value, which is invalid. We also model `can_pop_lead` as `True`, `False` and `None`, since `False` means "cannot pop lead" and is different from "no filter". The filters object itself can be omitted, in which case neither filter applies. How the two filters combine (AND semantics, one filter, no filters) is not a characteristic of its own: it follows from which blocks of A and B are selected, and the oracles check it. For the receiver state, the database contents decide the outcome, so we model whether the table has rows at all, and whether a stored pierce is `NULL`, which must never satisfy `min_pierce`. `sort_by` is interpolated into SQL, so we model not sorting, a whitelisted column and a hostile string. We model `limit` at its smallest valid value and below it, and the sort direction, which only matters once a sort column is given.

## ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`filters.min_pierce`|A) Threshold vs stored pierce values (1, 2, 3, 3)|A1: Below every value|`0`|
|||A2: Equal to an existing value (inclusive boundary)|`3`|
|||A3: One above the highest value|`4`|
|||A4: No filter|`None`|
|||A5: Negative (invalid)|`-1`|
|`filters.can_pop_lead`|B) Lead filter|B1: Must pop lead|`True`|
|||B2: Must not pop lead|`False`|
|||B3: No filter|`None`|
|`filters`|C) Filters object|C1: An `UpgradeFilters` instance|`UpgradeFilters(min_pierce=..., can_pop_lead=...)`|
|||C2: Omitted|`None`|
|`connection` (state: rows)|D) Table state|D1: Rows exist|the four-row fixture|
|||D2: Empty|schema only, no rows|
|`connection` (state: pierce)|E) Pierce values stored|E1: All non-`NULL`|the four-row fixture|
|||E2: One `NULL`|fixture plus Alchemist `0-0-1`|
|`sort_by`|F) Sort column|F1: No sort|`None`|
|||F2: Whitelisted column|`"projectile_pierce"`|
|||F3: Not whitelisted (hostile)|`"; DROP TABLE upgrades"`|
|`limit`|G) Limit|G1: No limit|`None`|
|||G2: Smallest valid|`1`|
|||G3: Below 1 (invalid)|`0`|
|`descending`|H) Sort direction|H1: Descending (the default)|`True`|
|||H2: Ascending|`False`|

Base case: A1, B2, C1, D1, E1, F1, G1, H1

Feasibility notes: C2 takes no filters, so A and B do not apply to it. H has no effect unless F is F2, so H2 cannot be varied alone from the base; it is covered by an extra non-BCC test. The base for A is `0` (A1) rather than `3` so that E2 is a meaningful test: with `min_pierce=0`, a `NULL` pierce would be wrongly included by an implementation that treats `NULL` as `0`, but is excluded by correct SQL comparison semantics.

## Base Choice Coverage

| BCC Test | A | B | C | D | E | F | G | H | Oracle | Test Name |
|---|---|---|---|---|---|---|---|---|---|---|
| T1 | A1 | B2 | C1 | D1 | E1 | F1 | G1 | H1 | `search_upgrades(conn, UpgradeFilters(min_pierce=0, can_pop_lead=False))` returns `["0-0-0", "1-1-0"]` | `test_search_upgrades_all_base` |
| T2 | A2 | B2 | C1 | D1 | E1 | F1 | G1 | H1 | `UpgradeFilters(min_pierce=3, can_pop_lead=False)` returns `["1-1-0"]` | `test_search_upgrades_pierce_inclusive_boundary` |
| T3 | A3 | B2 | C1 | D1 | E1 | F1 | G1 | H1 | `UpgradeFilters(min_pierce=4, can_pop_lead=False)` returns `[]` | `test_search_upgrades_pierce_above_highest` |
| T4 | A4 | B2 | C1 | D1 | E1 | F1 | G1 | H1 | `UpgradeFilters(min_pierce=None, can_pop_lead=False)` returns `["0-0-0", "1-1-0"]` | `test_search_upgrades_pierce_none` |
| T5 | A5 | B2 | C1 | D1 | E1 | F1 | G1 | H1 | `UpgradeFilters(min_pierce=-1, can_pop_lead=False)` raises `ValueError` | `test_search_upgrades_pierce_negative` |
| T6 | A1 | B1 | C1 | D1 | E1 | F1 | G1 | H1 | `UpgradeFilters(min_pierce=0, can_pop_lead=True)` returns `["2-0-0", "2-1-0"]` | `test_search_upgrades_lead_true` |
| T7 | A1 | B3 | C1 | D1 | E1 | F1 | G1 | H1 | `UpgradeFilters(min_pierce=0, can_pop_lead=None)` returns `["0-0-0", "1-1-0", "2-0-0", "2-1-0"]` | `test_search_upgrades_lead_none` |
| T8 | — | — | C2 | D1 | E1 | F1 | G1 | H1 | `search_upgrades(conn)` returns `["0-0-0", "1-1-0", "2-0-0", "2-1-0"]` | `test_search_upgrades_filters_omitted` |
| T9 | A1 | B2 | C1 | D2 | E1 | F1 | G1 | H1 | on the empty table, `UpgradeFilters(min_pierce=0, can_pop_lead=False)` returns `[]` | `test_search_upgrades_empty_table` |
| T10 | A1 | B2 | C1 | D1 | E2 | F1 | G1 | H1 | with Alchemist `0-0-1` inserted, `UpgradeFilters(min_pierce=0, can_pop_lead=False)` returns `["0-0-0", "1-1-0"]`; Alchemist `0-0-1` is absent | `test_search_upgrades_null_pierce` |
| T11 | A1 | B2 | C1 | D1 | E1 | F2 | G1 | H1 | base filters with `sort_by="projectile_pierce"` returns `["1-1-0", "0-0-0"]` | `test_search_upgrades_sort_whitelisted` |
| T12 | A1 | B2 | C1 | D1 | E1 | F3 | G1 | H1 | base filters with `sort_by="; DROP TABLE upgrades"` raises `ValueError`; afterward `SELECT COUNT(*) FROM upgrades` returns `4` | `test_search_upgrades_sort_not_whitelisted` |
| T13 | A1 | B2 | C1 | D1 | E1 | F1 | G2 | H1 | base filters with `limit=1` returns `["0-0-0"]` | `test_search_upgrades_limit_one` |
| T14 | A1 | B2 | C1 | D1 | E1 | F1 | G3 | H1 | base filters with `limit=0` raises `ValueError` | `test_search_upgrades_limit_zero` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T15 | A4 and B3 together (neither filter given) | `search_upgrades(conn, UpgradeFilters())` returns `["0-0-0", "1-1-0", "2-0-0", "2-1-0"]` | `test_search_upgrades_no_filters` |
| T16 | H1 with F2, tie-break, `NULL` last | with E2, `search_upgrades(conn, sort_by="projectile_pierce")` returns `["1-1-0", "2-1-0", "2-0-0", "0-0-0", Alchemist "0-0-1"]` | `test_search_upgrades_sort_descending_null_last` |
| T17 | H2 with F2, `NULL` last | with E2, `search_upgrades(conn, sort_by="projectile_pierce", descending=False)` returns `["0-0-0", "2-0-0", "1-1-0", "2-1-0", Alchemist "0-0-1"]` | `test_search_upgrades_sort_ascending_null_last` |
| T18 | #37 acceptance (F2 with G2-style limit) | `search_upgrades(conn, sort_by="projectile_pierce", limit=2)` returns `["1-1-0", "2-1-0"]` | `test_search_upgrades_sort_with_limit` |

## search_upgrades: `can_pop_*` filters (#34)

```python
def search_upgrades(connection, filters: UpgradeFilters | None = None, sort_by: str | None = None, descending: bool = True, limit: int | None = None) -> list[sqlite3.Row]
```

Keeps only upgrades whose damage type has each given `can_pop_<property>` flag equal to the given value. Same rules and fixture as the first section.

Flags of the fixture's damage types (from the `001_initial.sql` seed):

| damage_type | paths | lead | black | white | purple | glass | frozen |
|---|---|---|---|---|---|---|---|
| Sharp | `0-0-0` | 0 | 1 | 1 | 1 | 1 | 0 |
| Energy | `1-1-0` | 0 | 1 | 1 | 0 | 0 | 1 |
| Plasma | `2-0-0`, `2-1-0` | 1 | 1 | 1 | 0 | 0 | 1 |
| Unknown | D2 row only | `NULL` | `NULL` | `NULL` | `NULL` | `NULL` | `NULL` |

D2 only: add Alchemist `0-0-2`, `damage_type = Unknown`, other stats copied from Super Monkey `0-0-0` (inserted by hand). Alchemist sorts before Super Monkey, so if it were wrongly included it would appear first.

Take the `can_pop_*` fields of `UpgradeFilters`. The caller wants only upgrades whose damage type can (or cannot) pop a bloon property. There are six such fields, and each reads a different column, so we model which property is filtered, since a bug can map a field to the wrong column. We model the required value as `True` or `False`, since `False` means "cannot pop" and is a real restriction. A second flag must combine with the first by AND, so we model whether one is given. For the receiver state, the `Unknown` damage type stores `NULL` flags, which must match neither `True` nor `False`, so we model whether such a row exists.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`filters.can_pop_<property>`|A) Property filtered|A1: Lead|`can_pop_lead`|
|||A2: Black|`can_pop_black`|
|||A3: White|`can_pop_white`|
|||A4: Purple|`can_pop_purple`|
|||A5: Glass|`can_pop_glass`|
|||A6: Frozen|`can_pop_frozen`|
|`filters.can_pop_<property>` (value)|B) Required value|B1: Can pop|`True`|
|||B2: Cannot pop|`False`|
|`filters` (other `can_pop_*` fields)|C) Second flag|C1: None|other `can_pop_*` fields are `None`|
|||C2: A different property is also given|`can_pop_purple=True`|
|`connection` (state: damage types)|D) `Unknown` damage type stored|D1: No|the four-row fixture|
|||D2: Yes|fixture plus Alchemist `0-0-2`|

Base case: A1, B2, C1, D1

Feasibility notes: C2 names `can_pop_purple`, so it is infeasible with A4 (same property); the BCC pairs it only with A1.

### Base Choice Coverage

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B2 | C1 | D1 | `search_upgrades(conn, UpgradeFilters(can_pop_lead=False))` returns `["0-0-0", "1-1-0"]` | `test_search_upgrades_can_pop_lead_false` |
| T2 | A2 | B2 | C1 | D1 | `UpgradeFilters(can_pop_black=False)` returns `[]` | `test_search_upgrades_can_pop_black_false` |
| T3 | A3 | B2 | C1 | D1 | `UpgradeFilters(can_pop_white=False)` returns `[]` | `test_search_upgrades_can_pop_white_false` |
| T4 | A4 | B2 | C1 | D1 | `UpgradeFilters(can_pop_purple=False)` returns `["1-1-0", "2-0-0", "2-1-0"]` | `test_search_upgrades_can_pop_purple_false` |
| T5 | A5 | B2 | C1 | D1 | `UpgradeFilters(can_pop_glass=False)` returns `["1-1-0", "2-0-0", "2-1-0"]` | `test_search_upgrades_can_pop_glass_false` |
| T6 | A6 | B2 | C1 | D1 | `UpgradeFilters(can_pop_frozen=False)` returns `["0-0-0"]` | `test_search_upgrades_can_pop_frozen_false` |
| T7 | A1 | B1 | C1 | D1 | `UpgradeFilters(can_pop_lead=True)` returns `["2-0-0", "2-1-0"]` | `test_search_upgrades_can_pop_lead_true` |
| T8 | A1 | B2 | C2 | D1 | `UpgradeFilters(can_pop_lead=False, can_pop_purple=True)` returns `["0-0-0"]` | `test_search_upgrades_can_pop_two_flags` |
| T9 | A1 | B2 | C1 | D2 | with Alchemist `0-0-2` inserted, `UpgradeFilters(can_pop_lead=False)` returns `["0-0-0", "1-1-0"]`; Alchemist `0-0-2` is absent | `test_search_upgrades_can_pop_unknown_false` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T10 | B1 with D2 (`NULL` never matches `True` either) | with Alchemist `0-0-2` inserted, `UpgradeFilters(can_pop_lead=True)` returns `["2-0-0", "2-1-0"]`; Alchemist `0-0-2` is absent | `test_search_upgrades_can_pop_unknown_true` |
