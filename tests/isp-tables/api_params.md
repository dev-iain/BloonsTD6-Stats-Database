# Request parameter parsing (#76): `btd6/api/params.py`

## Rules for these tests

- Pure functions: no database. Tested in `tests/test_api_params.py`.
- Form keys (`form: dict[str, str | bool]`): `name`; one key per pop property (`lead`, `black`, `white`, `purple`, `glass`, `frozen`) holding `"any"`, `"can"`, `"cannot"` or a checkbox `bool`; `camo` holding `"either"`, `"yes"` or `"no"`; `min_range`, `min_pierce`, `min_damage`, `min_speed`; `damage_type`; `sort`; `limit`. A missing key behaves like its base value.
- A checkbox `True` means "can pop", `False` (unchecked) means no filter (`None`).
- Invalid input raises `QueryError` (the same class the query layer raises) whose message the API returns as a 422 `error` and the frontend shows inline. No `ValueError` from `float()` or `int()` may leak.
- `form_to_filters` does not set `category`; the UI searches every category present.
- Sort and limit are not `UpgradeFilters` fields (`search_upgrades` takes them as arguments), so they are parsed by the companion `form_to_search_options(form) -> tuple[str | None, int | None]`.

---

## 1. form_to_filters

```python
def form_to_filters(form: dict[str, str | bool]) -> UpgradeFilters
```

Converts raw widget text and choices into an `UpgradeFilters`, rejecting text a query could not use.

Take the function `form_to_filters`. The user wants every filter they filled in applied and every field they left alone ignored, so we model each field as blank, valid, or invalid. Numeric fields share one parser, so one field (`min_pierce`) is the representative for the blocks and a parametrized test repeats the base values across the other three. Pop choices decide a tri-state, and an unchecked checkbox must mean "no filter" rather than "cannot pop". Damage type is only forwarded: the query layer validates names, so "Any" must become `None` and a name must pass through unchanged. Finally we model a form that lacks keys, because the tab may build the dict incrementally.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`form["name"]`|A) Name text|A1: Blank|`""`|
|||A2: Text|`"wizard"`|
|||A3: Padded with spaces|`"  wizard  "`|
|||A4: Only spaces|`"   "`|
|`form["min_pierce"]`|B) Numeric text|B1: Blank|`""`|
|||B2: Positive number|`"3"`|
|||B3: Zero (boundary)|`"0"`|
|||B4: Not a number|`"abc"`|
|||B5: Negative|`"-1"`|
|||B6: Not finite|`"inf"`|
|||B7: Only spaces|`"  "`|
|`form["lead"]`|C) Pop choice|C1: Any|`"any"`|
|||C2: Can|`"can"`|
|||C3: Cannot|`"cannot"`|
|||C4: Checkbox unchecked|`False`|
|||C5: Checkbox checked|`True`|
|||C6: Unknown text|`"maybe"`|
|all six pop keys|D) All pop checkboxes|D1: Not all unchecked (base: all `"any"`)|every pop `"any"`|
|||D2: All six unchecked|every pop `False`|
|`form["camo"]`|E) Camo choice|E1: Either|`"either"`|
|||E2: Yes|`"yes"`|
|||E3: No|`"no"`|
|||E4: Unknown text|`"maybe"`|
|`form["damage_type"]`|F) Damage type|F1: Any|`"Any"`|
|||F2: A name|`"Plasma"`|
|||F3: Blank|`""`|
|`form`|G) Keys present|G1: Every key|full form|
|||G2: Empty dict|`{}`|

Base case: A1, B1, C1, D1, E1, F1, G1

Feasibility notes: D2 is the all-unchecked state and is checked for the whole filter; C4 and C5 vary one key. G2 cannot be combined with other blocks, since it has no keys. Numeric text is represented by `min_pierce`; one extra parametrized test (not BCC) repeats B2 and B5 on `min_range`, `min_damage` and `min_speed`, which map to `min_range`, `min_damage` and `min_projectile_speed`.

### Base Choice Coverage

| BCC Test | A | B | C | D | E | F | G | Oracle | Test Name |
|---|---|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | F1 | G1 | returns `UpgradeFilters()` (every field `None`) | `test_form_to_filters_all_base` |
| T2 | A2 | B1 | C1 | D1 | E1 | F1 | G1 | `tower_name_contains == "wizard"`, all else `None` | `test_form_to_filters_name_text` |
| T3 | A3 | B1 | C1 | D1 | E1 | F1 | G1 | `tower_name_contains == "wizard"` | `test_form_to_filters_name_padded` |
| T4 | A4 | B1 | C1 | D1 | E1 | F1 | G1 | `tower_name_contains is None` | `test_form_to_filters_name_only_spaces` |
| T5 | A1 | B2 | C1 | D1 | E1 | F1 | G1 | `min_pierce == 3.0` | `test_form_to_filters_number_positive` |
| T6 | A1 | B3 | C1 | D1 | E1 | F1 | G1 | `min_pierce == 0.0` (not `None`) | `test_form_to_filters_number_zero` |
| T7 | A1 | B4 | C1 | D1 | E1 | F1 | G1 | raises `QueryError("min_pierce must be a number, got 'abc'")` | `test_form_to_filters_number_not_a_number` |
| T8 | A1 | B5 | C1 | D1 | E1 | F1 | G1 | raises `QueryError("min_pierce must be 0 or more, got -1.0")` | `test_form_to_filters_number_negative` |
| T9 | A1 | B6 | C1 | D1 | E1 | F1 | G1 | raises `QueryError("min_pierce must be a number, got 'inf'")` | `test_form_to_filters_number_not_finite` |
| T10 | A1 | B7 | C1 | D1 | E1 | F1 | G1 | `min_pierce is None` | `test_form_to_filters_number_only_spaces` |
| T11 | A1 | B1 | C2 | D1 | E1 | F1 | G1 | `can_pop_lead is True` | `test_form_to_filters_pop_can` |
| T12 | A1 | B1 | C3 | D1 | E1 | F1 | G1 | `can_pop_lead is False` | `test_form_to_filters_pop_cannot` |
| T13 | A1 | B1 | C4 | D1 | E1 | F1 | G1 | `can_pop_lead is None` | `test_form_to_filters_pop_checkbox_unchecked` |
| T14 | A1 | B1 | C5 | D1 | E1 | F1 | G1 | `can_pop_lead is True` | `test_form_to_filters_pop_checkbox_checked` |
| T15 | A1 | B1 | C6 | D1 | E1 | F1 | G1 | raises `QueryError('lead must be any, can or cannot, got "maybe"')` | `test_form_to_filters_pop_unknown_text` |
| T16 | A1 | B1 | C1 | D2 | E1 | F1 | G1 | returns `UpgradeFilters()` | `test_form_to_filters_all_checkboxes_unchecked` |
| T17 | A1 | B1 | C1 | D1 | E2 | F1 | G1 | `can_hit_camo is True` | `test_form_to_filters_camo_yes` |
| T18 | A1 | B1 | C1 | D1 | E3 | F1 | G1 | `can_hit_camo is False` | `test_form_to_filters_camo_no` |
| T19 | A1 | B1 | C1 | D1 | E4 | F1 | G1 | raises `QueryError('camo must be either, yes or no, got "maybe"')` | `test_form_to_filters_camo_unknown_text` |
| T20 | A1 | B1 | C1 | D1 | E1 | F2 | G1 | `damage_type == "Plasma"` | `test_form_to_filters_damage_type_name` |
| T21 | A1 | B1 | C1 | D1 | E1 | F3 | G1 | `damage_type is None` | `test_form_to_filters_damage_type_blank` |
| T22 | A1 | B1 | C1 | D1 | E1 | F1 | G2 | returns `UpgradeFilters()` | `test_form_to_filters_empty_form` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T23 | B2 and B5 on the other three numeric fields | `min_range`, `min_damage`, `min_projectile_speed` get `3.0`; `-1` raises `QueryError` naming the form key | `test_form_to_filters_each_numeric_field` |
| T24 | several filters together | the example "cannot pop lead, min pierce 3" gives `can_pop_lead=False, min_pierce=3.0` | `test_form_to_filters_epic_example` |
| T25 | invariant (hypothesis) | any text either returns filters whose `min_pierce` is `None` or finite and `>= 0`, or raises `QueryError`; never any other exception | `test_form_to_filters_never_leaks_other_exceptions` |

---

## 2. form_to_search_options

```python
def form_to_search_options(form: dict[str, str | bool]) -> tuple[str | None, int | None]
```

Returns `(sort_by, limit)` from the `sort` and `limit` form values. `sort` must be in `query.SORT_COLUMNS`; `limit` must be a whole number of at least 1.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`form["sort"]`|A) Sort value|A1: Blank|`""`|
|||A2: Allowed column|`"projectile_pierce"`|
|||A3: Not allowed|`"bogus"`|
|`form["limit"]`|B) Limit text|B1: Blank|`""`|
|||B2: Smallest valid (boundary)|`"1"`|
|||B3: Zero (boundary)|`"0"`|
|||B4: Negative|`"-3"`|
|||B5: Not a number|`"abc"`|
|||B6: Fractional|`"2.5"`|
|||B7: Large valid|`"500"`|

Base case: A1, B1

### Base Choice Coverage

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | returns `(None, None)` | `test_form_to_search_options_all_base` |
| T2 | A2 | B1 | returns `("projectile_pierce", None)` | `test_form_to_search_options_sort_allowed` |
| T3 | A3 | B1 | raises `QueryError` whose message starts `Cannot sort by "bogus". Allowed:` | `test_form_to_search_options_sort_not_allowed` |
| T4 | A1 | B2 | returns `(None, 1)` | `test_form_to_search_options_limit_one` |
| T5 | A1 | B3 | raises `QueryError("limit must be at least 1, got 0")` | `test_form_to_search_options_limit_zero` |
| T6 | A1 | B4 | raises `QueryError("limit must be at least 1, got -3")` | `test_form_to_search_options_limit_negative` |
| T7 | A1 | B5 | raises `QueryError("limit must be a whole number, got 'abc'")` | `test_form_to_search_options_limit_not_a_number` |
| T8 | A1 | B6 | raises `QueryError("limit must be a whole number, got '2.5'")` | `test_form_to_search_options_limit_fractional` |
| T9 | A1 | B7 | returns `(None, 500)` | `test_form_to_search_options_limit_large` |

---

## 3. rows_to_cells

```python
def rows_to_cells(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, ...]]
```

Formats result rows for the table: one tuple per row with the `TABLE_CELL_COLUMNS` (`tower_name`, `path`, `attack_rate`, `projectile_count`, `projectile_damage`, `projectile_pierce`, `projectile_speed`) through `format_cell`, then a combined Pops cell. Rows are built with `ResultRowFactory`. Each row equals `btd6.formatting.format_row(row)`; the oracles below are the literal text.

Take the function `rows_to_cells`. The player wants a table they can scan, so we model how many rows arrive (none must give an empty list, not an error). Each cell goes through `format_cell`, so we model a `NULL` stat (`-`), a whole float (`2.0` prints `2`) and a fractional float (`0.045` stays). The Pops cell combines six 0/1/`NULL` flags, so we model all set (`All`), none set (`-`), some set (codes in lead, black, white, purple, glass, frozen order) and `NULL` flags (the `Unknown` damage type; `-`, never `no`). The `yes`/`no` text of booleans is the flag-column branch of `format_cell`; the table has no standalone boolean column, so it is exercised through the Pops flags and checked on `format_cell` directly.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`rows`|A) Number of rows|A1: One|one default row|
|||A2: None|`[]`|
|||A3: Several, order kept|rows `0-0-0`, `1-1-0`|
|`rows` (stat)|B) `projectile_pierce`|B1: Whole float|`3.0`|
|||B2: `NULL`|`None`|
|||B3: Fractional float|`0.5`|
|`rows` (rate)|C) `attack_rate`|C1: Fractional float|`0.045`|
|||C2: Whole float|`1.0`|
|`rows` (flags)|D) Pop flags|D1: All six set|all `1`|
|||D2: None set|all `0`|
|||D3: Some set|lead and glass `1`, rest `0`|
|||D4: All `NULL`|all `None`|

Base case: A1, B1, C1, D1

### Base Choice Coverage

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | `[("Super Monkey", "0-0-0", "0.045", "1", "2", "3", "200", "All")]` | `test_rows_to_cells_all_base` |
| T2 | A2 | - | - | - | `[]` | `test_rows_to_cells_no_rows` |
| T3 | A3 | B1 | C1 | D1 | two tuples, paths `0-0-0` then `1-1-0` | `test_rows_to_cells_several_rows_keep_order` |
| T4 | A1 | B2 | C1 | D1 | pierce cell is `"-"` | `test_rows_to_cells_null_stat` |
| T5 | A1 | B3 | C1 | D1 | pierce cell is `"0.5"` | `test_rows_to_cells_fractional_stat` |
| T6 | A1 | B1 | C2 | D1 | rate cell is `"1"` | `test_rows_to_cells_whole_float_rate` |
| T7 | A1 | B1 | C1 | D2 | Pops cell is `"-"` | `test_rows_to_cells_no_pops` |
| T8 | A1 | B1 | C1 | D3 | Pops cell is `"Ld Gl"` | `test_rows_to_cells_some_pops` |
| T9 | A1 | B1 | C1 | D4 | Pops cell is `"-"` | `test_rows_to_cells_null_pops` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T10 | booleans (`format_cell` flag branch) | `format_cell("can_hit_camo", 1) == "yes"`, `(…, 0) == "no"`, `(…, None) == "-"` | `test_format_cell_flags_yes_no` |
| T11 | invariant (hypothesis) | `len(result) == len(rows)`, every tuple has 8 cells (`len(TABLE_COLUMNS)`), all `str` | `test_rows_to_cells_shape_invariant` |
| T12 | real query rows | `rows_to_cells(search_upgrades(...))` equals `run_query` output for the same filters | `test_rows_to_cells_matches_run_query` |

---
