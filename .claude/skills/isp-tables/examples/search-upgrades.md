# Example: `search_upgrades(connection, can_pop_lead: bool | None, min_pierce: int | None) -> list[Row]`

Note: this function is planned (Nicole's query layer), so this example illustrates the process; the real signature may differ. Take the function `search_upgrades`, whose ISP is provided below. First, we use interface-based modeling; we know that the function takes in two optional filters, thus we model the characteristics of each. To determine important characteristics, we first fixate on the function of the code: the caller wants only the upgrades that satisfy every filter they gave, and a filter left as `None` must not restrict anything. We know that `min_pierce` is compared against the `projectile_pierce` column, thus we model its position relative to the stored values, with boundary values on both sides of a real value, because off-by-one errors (`>` versus `>=`) are the most likely bug. We also model `can_pop_lead` as `True`, `False` and `None`, since `False` means "cannot pop lead" and is different from "no filter". The interaction between the filters (AND semantics, one filter, no filters) is not a characteristic of its own: it follows from which blocks of the two filter characteristics are selected, and the oracles check it. For the receiver state, the database contents decide the outcome, so we model whether the table has rows at all. Finally, some stats can be `NULL` (for example `ability_cooldown`, and any future stat an upgrade does not have), so we model a `NULL` pierce, which must never satisfy `min_pierce`.

Test fixture: a small in-memory DB seeded with four real rows from `data.csv`, so every expected result can be read off by hand.

| path | projectile_pierce | can_pop_lead | damage_type |
|---|---|---|---|
| `0-0-0` | 1 | False | Sharp |
| `2-0-0` | 2 | True | Plasma |
| `1-1-0` | 3 | False | Energy |
| `2-1-0` | 3 | True | Plasma |

## ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`min_pierce`|A) Threshold vs stored pierce values (1, 2, 3, 3)|A1: Below every value|`0`|
|||A2: Equal to an existing value (inclusive boundary)|`3`|
|||A3: One above the highest value|`4`|
|||A4: No filter|`None`|
|`can_pop_lead`|B) Lead filter|B1: Must pop lead|`True`|
|||B2: Must not pop lead|`False`|
|||B3: No filter|`None`|
|`connection` (state: rows)|C) Table state|C1: Rows exist|the four-row fixture|
|||C2: Empty table|schema only, no rows|
|`connection` (state: rows)|D) `NULL` pierce|D1: No `NULL` pierce|the four-row fixture|
|||D2: A row has `NULL` pierce|extra row `0-0-1` inserted with `projectile_pierce = NULL`, `can_pop_lead = False`|

Base case: A1, B2, C1, D1

Feasibility notes: use an in-memory SQLite DB, never a mock. C2 makes A, B and D irrelevant, so it is tested once. `data.csv` has no `NULL` pierce, so D2 needs a row inserted explicitly. "Rows exist but none match" is not a separate block: it is the result of A3 against this fixture.

## Base Choice Coverage

The base for A is `0` (A1) rather than `3` so that D2 is a meaningful test: with `min_pierce=0`, a row whose pierce is `NULL` would be wrongly included by an implementation that treats `NULL` as `0`, but excluded by correct SQL comparison semantics. Results are compared as sets of `path` values, since the order is not specified.

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B2 | C1 | D1 | `search_upgrades(conn, can_pop_lead=False, min_pierce=0)` returns paths `{"0-0-0", "1-1-0"}` | `test_search_upgrades_all_base` |
| T2 | A2 | B2 | C1 | D1 | `search_upgrades(conn, can_pop_lead=False, min_pierce=3)` returns paths `{"1-1-0"}` | `test_search_upgrades_pierce_inclusive_boundary` |
| T3 | A3 | B2 | C1 | D1 | `search_upgrades(conn, can_pop_lead=False, min_pierce=4)` returns `[]` | `test_search_upgrades_pierce_above_highest` |
| T4 | A4 | B2 | C1 | D1 | `search_upgrades(conn, can_pop_lead=False, min_pierce=None)` returns paths `{"0-0-0", "1-1-0"}` | `test_search_upgrades_pierce_none` |
| T5 | A1 | B1 | C1 | D1 | `search_upgrades(conn, can_pop_lead=True, min_pierce=0)` returns paths `{"2-0-0", "2-1-0"}` | `test_search_upgrades_lead_true` |
| T6 | A1 | B3 | C1 | D1 | `search_upgrades(conn, can_pop_lead=None, min_pierce=0)` returns paths `{"0-0-0", "2-0-0", "1-1-0", "2-1-0"}` | `test_search_upgrades_lead_none` |
| T7 | A1 | B2 | C2 | D1 | `search_upgrades(conn, can_pop_lead=False, min_pierce=0)` returns `[]` | `test_search_upgrades_empty_table` |
| T8 | A1 | B2 | C1 | D2 | with `0-0-1` inserted, `search_upgrades(conn, can_pop_lead=False, min_pierce=0)` returns paths `{"0-0-0", "1-1-0"}`; `"0-0-1"` is absent | `test_search_upgrades_null_pierce` |

Extra non-BCC test T9 (A4 and B3 together, which BCC cannot generate because it changes one block at a time): `search_upgrades(conn, can_pop_lead=None, min_pierce=None)` returns all four fixture paths; Test Name `test_search_upgrades_no_filters`. T4 returns the same set as T1 because every stored pierce is at least 1; it is still required, since it proves that `None` adds no restriction.
