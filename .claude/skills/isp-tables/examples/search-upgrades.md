# Example: `search_upgrades(connection, can_pop_lead: bool | None, min_pierce: int | None) -> list[Row]`

Note: this function is planned (Nicole's query layer), so this example illustrates the process; the real signature may differ. Take the function `search_upgrades`, whose ISP is provided below. First, we use interface-based modeling; we know that the function takes in two optional filters, thus we model the characteristics of each. To determine important characteristics, we first fixate on the function of the code: the caller wants only the upgrades that satisfy every filter they gave, and a filter left as `None` must not restrict anything. We know that `min_pierce` is compared against the `projectile_pierce` column, thus we first have to model its position relative to the stored values, with boundary values on both sides of a real value, because off-by-one errors (`>` versus `>=`) are the most likely bug. We also model `can_pop_lead` as `True`, `False` and `None`, since `False` means "cannot pop lead" and is different from "no filter". Next, we know that the result depends on the filters together, not on each alone, thus we model the interaction: both given (AND semantics), only one given, and neither given. For the receiver state, the database contents decide the outcome, so we model whether the table has rows at all. Finally, some stats can be `NULL` (for example `ability_cooldown`, and any future stat an upgrade does not have), so we model a `NULL` pierce, which must never satisfy `min_pierce`.

Test fixture: a small in-memory DB seeded with four real rows from `data.csv`, so every expected result can be read off by hand.

| path | projectile_pierce | can_pop_lead | damage_type |
|---|---|---|---|
| `0-0-0` | 1 | False | Sharp |
| `2-0-0` | 2 | True | Plasma |
| `1-1-0` | 3 | False | Energy |
| `2-1-0` | 3 | True | Plasma |

## ISP

| Parameter | Characteristic | Partition | Value |
|---|---|---|---|
| `min_pierce` | A) Threshold vs stored pierce values (1, 2, 3, 3) | A1: Below every value (Base) | `0` |
||| A2: Equal to an existing value (inclusive boundary) | `3` |
||| A3: One above the highest value | `4` |
||| A4: No filter | `None` |
| `can_pop_lead` | B) Lead filter | B1: Must pop lead | `True` |
||| B2: Must not pop lead (Base) | `False` |
||| B3: No filter | `None` |
| both filters | C) Filter combination | C1: Both given (AND) | `min_pierce=3, can_pop_lead=False` -> only `1-1-0` |
||| C2: Only one given | `min_pierce=3, can_pop_lead=None` -> `1-1-0`, `2-1-0` |
||| C3: Neither given | `None, None` -> every row |
| database | D) Table state | D1: Rows exist (Base) | the four-row fixture |
||| D2: Empty table | schema only, no rows |
| database | E) Pierce value | E1: Non-null (Base) | the four-row fixture |
||| E2: `NULL` | extra row `0-0-1` inserted with `projectile_pierce = NULL`, `can_pop_lead = False` |

Feasibility notes: use an in-memory SQLite DB, never a mock. D2 makes A to C irrelevant, so it is tested once. `data.csv` has no `NULL` pierce, so E2 needs a row inserted explicitly. "Rows exist but none match" is not a separate block: it is the result of A3 against this fixture.

## Base Choice Coverage

Characteristic C is not varied independently: it is determined by A and B (which of them is `None`). C1 is the all-base case, C2 is covered by changing A to A4 or B to B3, and C3 (neither filter) needs two changes at once, so BCC cannot generate it. Add it as one extra non-BCC test. BCC is therefore taken over A, B, D and E.

The base for A is `0` (A1) rather than `3` so that E2 is a meaningful test: with `min_pierce=0`, a row whose pierce is `NULL` would be wrongly included by an implementation that treats `NULL` as `0`, but excluded by correct SQL comparison semantics. Results are compared as sets of `path` values, since the order is not specified.

| Case ID | A selection | B selection | D selection | E selection | Changed characteristic | Expected result |
| ------- | ----------- | ----------- | ----------- | ----------- | ---------------------- | --------------- |
| BCC-1 | A1 | B2 | D1 | E1 | None — All Base | `search_upgrades(conn, can_pop_lead=False, min_pierce=0)` returns paths `{"0-0-0", "1-1-0"}` |
| BCC-2 | A2 | B2 | D1 | E1 | A | `search_upgrades(conn, can_pop_lead=False, min_pierce=3)` returns paths `{"1-1-0"}` |
| BCC-3 | A3 | B2 | D1 | E1 | A | `search_upgrades(conn, can_pop_lead=False, min_pierce=4)` returns `[]` |
| BCC-4 | A4 | B2 | D1 | E1 | A | `search_upgrades(conn, can_pop_lead=False, min_pierce=None)` returns paths `{"0-0-0", "1-1-0"}` |
| BCC-5 | A1 | B1 | D1 | E1 | B | `search_upgrades(conn, can_pop_lead=True, min_pierce=0)` returns paths `{"2-0-0", "2-1-0"}` |
| BCC-6 | A1 | B3 | D1 | E1 | B | `search_upgrades(conn, can_pop_lead=None, min_pierce=0)` returns paths `{"0-0-0", "2-0-0", "1-1-0", "2-1-0"}` |
| BCC-7 | A1 | B2 | D2 | E1 | D | `search_upgrades(conn, can_pop_lead=False, min_pierce=0)` returns `[]` |
| BCC-8 | A1 | B2 | D1 | E2 | E | with `0-0-1` inserted, `search_upgrades(conn, can_pop_lead=False, min_pierce=0)` returns paths `{"0-0-0", "1-1-0"}`; `"0-0-1"` is absent |

Extra non-BCC test (C3): `search_upgrades(conn, can_pop_lead=None, min_pierce=None)` returns all four fixture paths. BCC-4 returns the same set as BCC-1 because every stored pierce is at least 1; it is still required, since it proves that `None` adds no restriction.
