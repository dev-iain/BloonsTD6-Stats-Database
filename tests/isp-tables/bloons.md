# Bloon data: `fetch_bloons`, `extract_bloon_rows` and `split_bloon_name`

## Rules for these tests

- `fetch_bloons` lives in `btd6/etl/fetch.py`; `extract_bloon_rows` and `split_bloon_name` live in `btd6/etl/extract.py`.
- `fetch_bloons` calls `wiki_api(action="cargoquery", tables="btd6_bloons", fields="id,name,health,health_fort,layers,rbe,rbe_fort,is_moab,speed,immunity,parent_of,child_of", limit=500, offset=<n>)`. Tests monkeypatch `btd6.etl.fetch.wiki_api` with a fake that records its keyword arguments and returns canned pages; they never hit the wiki.
- Each page is `{"cargoquery": [{"title": {...}}, ...]}`. `fetch_bloons` unwraps every entry to its `title` dict and returns the rows of all pages in order, with every value left as the wiki gave it (only the keys are normalized, see below) (Cargo returns every value as a string).
- Pagination: start at `offset=0`; while the page just read held `limit` (500) rows, request `offset += 500`; stop at the first page with fewer than `limit` rows (an empty page counts).
- A response with an `error` key raises `ValueError("Wiki cargo query failed: <error>")`, the same message as `cargo_rows`. An empty result on the first page raises `ValueError("Wiki cargo query returned no rows")`. HTTP errors are not caught: `requests.HTTPError` from `wiki_api` propagates.
- `extract_bloon_rows` output keys, in order: `name, health, health_fort, layers, rbe, rbe_fort, is_moab, speed`. The display `name`, `immunity`, `parent_of` and `child_of` are not stored; `name` in the output holds the Cargo `id` (the schema keeps only what the round queries need).
- Types: `health, health_fort, layers, rbe, rbe_fort` are `int`, `speed` is `float`, `is_moab` is `bool` (`"0"` -> `False`, `"1"` -> `True`). An empty string or a missing key becomes `None`, except `is_moab`, which is `NOT NULL` in the schema, so empty or missing `is_moab` becomes `False`. Any other non-numeric text raises `ValueError` naming the bloon and the field.
- The output `name` is the Cargo `id` column (`Red`, `Moab`, `Ddt`, `Zomg`, `Bad`), not the display `name` (`Red Bloon`, `MOAB`), because the roundset uses the `id` spelling. The display name is dropped. The `id` is stripped of surrounding whitespace and is required; the wiki table holds base bloons only, so modifiers are never split here.
- The live Cargo response spells multi-word keys with spaces (`health fort`, `rbe fort`, `is moab`, `parent of`, `child of`). `fetch_bloons` normalizes every key by replacing spaces with underscores (`test_fetch_bloons_normalizes_spaced_keys`); values stay untouched.
- Open decisions to confirm before the tests are written: the `is_moab` empty -> `False` rule; that `fetch_bloons` raises on an empty first page (matches `cargo_rows`).

---

## fetch_bloons

```python
def fetch_bloons() -> list[dict[str, str]]
```

Reads the whole `btd6_bloons` Cargo table page by page and returns the unwrapped rows.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`wiki_api` responses|A) Pages needed|A1: One short page **(Base)**|one page of 3 rows (`Red`, `Blue`, `Green`)|
|||A2: No rows|`{"cargoquery": []}`|
|||A3: Exactly one full page, then an empty page|page 1 has 500 rows, page 2 is `{"cargoquery": []}`|
|||A4: One full page, then a short page|page 1 has 500 rows, page 2 has 120 rows|
|`wiki_api` responses|B) Response status|B1: Normal **(Base)**|no `error` key|
|||B2: Cargo error|`{"error": {"code": "internal_api_error", "info": "Table missing"}}`|
|||B3: HTTP error|fake raises `requests.HTTPError("503")`|
|`wiki_api` responses|C) Row fields|C1: All twelve fields present **(Base)**|`{"id": "red", "name": "Red", "health": "1", ..., "child_of": ""}`|
|||C2: A field missing from the row|`speed` key absent from the `Blue` title dict|

Base case: A1, B1, C1

Excluded or reduced combinations: B2 and B3 stop the first request, so A is moot for them (base A1 is kept). B2 on the second page is a non-BCC test.

### BCC

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | returns 3 dicts with `name` `Red`, `Blue`, `Green` in that order, each equal to its `title` dict; `wiki_api` called once with `action="cargoquery"`, `tables="btd6_bloons"`, the twelve-field `fields` string, `limit=500`, `offset=0` | `test_fetch_bloons_single_page` |
| T2 | A2 | B1 | C1 | raises `ValueError`: `Wiki cargo query returned no rows` | `test_fetch_bloons_empty_result` |
| T3 | A3 | B1 | C1 | returns 500 rows; `wiki_api` called twice with `offset` 0 then 500 | `test_fetch_bloons_exact_full_page` |
| T4 | A4 | B1 | C1 | returns 620 rows in page order (first row of page 2 is row 501); `offset` values were 0 and 500 | `test_fetch_bloons_two_pages` |
| T5 | A1 | B2 | C1 | raises `ValueError` whose message starts `Wiki cargo query failed:` and contains `Table missing` | `test_fetch_bloons_cargo_error` |
| T6 | A1 | B3 | C1 | raises `requests.HTTPError` | `test_fetch_bloons_http_error` |
| T7 | A1 | B1 | C2 | returns the three rows; the `Blue` dict has no `speed` key (passed through unchanged, not filled in) | `test_fetch_bloons_missing_field_passes_through` |

Extra tests, not BCC: an `error` on page 2 after a full page 1 raises `ValueError` and returns no partial rows (`test_fetch_bloons_error_on_second_page`); `fetch_bloons` never calls `requests` directly (`wiki_api` is the only network entry point).

---

## extract_bloon_rows

```python
def extract_bloon_rows(raw: list[dict[str, str]]) -> list[dict[str, Any]]
```

Turns the string-valued Cargo rows into typed rows ready for `load_bloons`.

### ISP

Base row `RED`: `{"id": "Red", "name": "Red Bloon", "health": "1", "health_fort": "2", "layers": "1", "rbe": "1", "rbe_fort": "2", "is_moab": "0", "speed": "1.0", "immunity": "", "parent_of": "", "child_of": ""}`.

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`raw`|A) Number of rows|A1: Several **(Base)**|`[RED, MOAB]` (`id` `Moab`, `name` `MOAB`: health `"200"`, rbe `"616"`, `is_moab` `"1"`, speed `"1.0"`)|
|||A2: Empty|`[]`|
|||A3: One|`[RED]`|
|`raw` (health)|B) Numeric field `health`|B1: Integer text **(Base)**|`"1"`|
|||B2: Empty string|`""`|
|||B3: Key missing|no `health` key|
|||B4: Not a number|`"abc"`|
|`raw` (speed)|C) Decimal field `speed`|C1: Decimal text **(Base)**|`"1.0"`|
|||C2: Whole-number text|`"2"`|
|||C3: Empty string|`""`|
|`raw` (is_moab)|D) `is_moab` text|D1: `"0"` **(Base)**|`"0"`|
|||D2: `"1"`|`"1"`|
|||D3: Empty string|`""`|
|||D4: Anything else|`"2"`|
|`raw` (id)|E) Name (Cargo `id`, becomes output `name`)|E1: Plain base name **(Base)**|`"Red"`|
|||E2: Abbreviated or odd casing|`"Ddt"`, `"Zomg"`|
|||E3: Padded with whitespace|`" Red "`|
|||E4: Contains a modifier word, not split here|`"RedCamo"`|
|||E5: Empty|`""`|

Base case: A1, B1, C1, D1, E1

Excluded or reduced combinations: `health_fort`, `layers`, `rbe` and `rbe_fort` share the integer code path of `health`, so they are covered by T1 (all converted) and one parametrized test, not by their own characteristics.

### BCC

| BCC Test | A | B | C | D | E | Oracle | Test Name |
|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | two rows; first equals `{"name": "Red", "health": 1, "health_fort": 2, "layers": 1, "rbe": 1, "rbe_fort": 2, "is_moab": False, "speed": 1.0}` with exactly those keys in that order; types are `int`, `float`, `bool` | `test_extract_bloon_rows_base` |
| T2 | A2 | B1 | C1 | D1 | E1 | returns `[]` | `test_extract_bloon_rows_empty` |
| T3 | A3 | B1 | C1 | D1 | E1 | one row, `name` `Red` | `test_extract_bloon_rows_single` |
| T4 | A1 | B2 | C1 | D1 | E1 | first row `health` is `None`; other fields unchanged | `test_extract_bloon_rows_empty_health_is_none` |
| T5 | A1 | B3 | C1 | D1 | E1 | first row `health` is `None` | `test_extract_bloon_rows_missing_health_is_none` |
| T6 | A1 | B4 | C1 | D1 | E1 | raises `ValueError` mentioning `Red` and `health` | `test_extract_bloon_rows_non_numeric_health` |
| T7 | A1 | B1 | C2 | D1 | E1 | first row `speed` is `2.0` and a `float` | `test_extract_bloon_rows_speed_whole_number_is_float` |
| T8 | A1 | B1 | C3 | D1 | E1 | first row `speed` is `None` | `test_extract_bloon_rows_empty_speed_is_none` |
| T9 | A1 | B1 | C1 | D2 | E1 | second row (`Moab`) has `is_moab` `True` (`is True`, not `1`) | `test_extract_bloon_rows_is_moab_true` |
| T10 | A1 | B1 | C1 | D3 | E1 | first row `is_moab` is `False` | `test_extract_bloon_rows_empty_is_moab_is_false` |
| T11 | A1 | B1 | C1 | D4 | E1 | raises `ValueError` mentioning `is_moab` and `"2"` | `test_extract_bloon_rows_invalid_is_moab` |
| T12 | A1 | B1 | C1 | D1 | E2 | names `Ddt` and `Zomg` come back unchanged (casing kept) | `test_extract_bloon_rows_odd_names_kept` |
| T13 | A1 | B1 | C1 | D1 | E3 | first row `name` is `"Red"` | `test_extract_bloon_rows_name_stripped` |
| T14 | A1 | B1 | C1 | D1 | E4 | first row `name` is `"RedCamo"` (not split, no flags added) | `test_extract_bloon_rows_modifier_name_not_split` |
| T15 | A1 | B1 | C1 | D1 | E5 | raises `ValueError` mentioning `name` (the `id` is empty) | `test_extract_bloon_rows_empty_name` |

Extra tests, not BCC: `health_fort`, `layers`, `rbe` and `rbe_fort` each convert and each map `""` to `None` (parametrized, `test_extract_bloon_rows_integer_fields`); `immunity`, `parent_of`, `child_of` and `id` are absent from the output; the input list is not mutated; a Hypothesis property that for any integer `n` in 0-10^6 a row with `health=str(n)` returns `health == n`.

---

## split_bloon_name

```python
def split_bloon_name(name: str) -> tuple[str, bool, bool, bool]
```

Splits a roundset bloon name into `(base_name, is_camo, is_regrow, is_fortified)`.

Parsing rule: strip the case-sensitive suffixes `Fortified`, `Camo` and `Regrow` from the **end** of the name, repeatedly, in any order, until none is left; each stripped suffix sets its flag. The remainder is the base name and must not be empty. The wiki writes them as `<Base>[Regrow][Camo][Fortified]`. The rule is purely textual: it does not check whether the combination exists in the game (a `CeramicRegrow` splits like any other). A modifier word anywhere but the end of the name is part of the base name.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`name`|A) Modifier suffixes present|A1: None **(Base)**|`"Red"`|
|||A2: Camo only|`"RedCamo"`|
|||A3: Regrow only|`"BlueRegrow"`|
|||A4: Fortified only|`"MoabFortified"`|
|||A5: Regrow and Camo|`"GreenRegrowCamo"`|
|||A6: Camo and Fortified|`"CeramicCamoFortified"`|
|||A7: All three|`"CeramicRegrowCamoFortified"`|
|`name`|B) Shape of the name|B1: Ordinary base followed by suffixes **(Base)**|`"Red"`|
|||B2: Empty|`""`|
|||B3: A modifier word only, no base|`"Camo"`|
|||B4: Modifier text not at the end|`"CamoRed"`|
|||B5: Modifier text is a longer word|`"Camouflage"`|
|||B6: Wrong letter case|`"redcamo"`|

Base case: A1, B1

Excluded or reduced combinations: A is about which suffixes are present, so B2 to B6 (which have a fixed text) are tested with their own text and the suffix block they happen to land in; the oracle states it. The base-bloon identity (`Red`, `Moab`, `Ddt`, `Zomg`, `Bfb`, `Bad`, `Ceramic`) does not change the algorithm, so it is covered by a parametrized non-BCC test.

### BCC

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | returns `("Red", False, False, False)` | `test_split_bloon_name_plain` |
| T2 | A2 | B1 | `"RedCamo"` returns `("Red", True, False, False)` | `test_split_bloon_name_camo` |
| T3 | A3 | B1 | `"BlueRegrow"` returns `("Blue", False, True, False)` | `test_split_bloon_name_regrow` |
| T4 | A4 | B1 | `"MoabFortified"` returns `("Moab", False, False, True)` | `test_split_bloon_name_fortified` |
| T5 | A5 | B1 | `"GreenRegrowCamo"` returns `("Green", True, True, False)` | `test_split_bloon_name_regrow_camo` |
| T6 | A6 | B1 | `"CeramicCamoFortified"` returns `("Ceramic", True, False, True)` | `test_split_bloon_name_camo_fortified` |
| T7 | A7 | B1 | `"CeramicRegrowCamoFortified"` returns `("Ceramic", True, True, True)` | `test_split_bloon_name_all_modifiers` |
| T8 | A1 | B2 | raises `ValueError` mentioning an empty bloon name | `test_split_bloon_name_empty` |
| T9 | A2 | B3 | `"Camo"` raises `ValueError` (modifier with no base bloon) | `test_split_bloon_name_modifier_only` |
| T10 | A1 | B4 | `"CamoRed"` returns `("CamoRed", False, False, False)` | `test_split_bloon_name_modifier_prefix_kept` |
| T11 | A1 | B5 | `"Camouflage"` returns `("Camouflage", False, False, False)` | `test_split_bloon_name_longer_word_not_split` |
| T12 | A1 | B6 | `"redcamo"` returns `("redcamo", False, False, False)` (case-sensitive) | `test_split_bloon_name_case_sensitive` |

Extra tests, not BCC:

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T13 | base-bloon identity | `Ddt`/`DdtCamo`, `Zomg`/`ZomgFortified`, `Bfb`, `Bad`, `Moab` with `Fortified` all give the same base name with the right flags (parametrized) | `test_split_bloon_name_base_bloons` |
| T14 | suffix order | `"BlueCamoRegrow"` returns `("Blue", True, True, False)` (order does not matter) | `test_split_bloon_name_suffix_order_irrelevant` |
| T15 | all names in the real round fixture | every `bloon` in `tests/fixtures/default_roundset_first10.json` splits without error and the base is an extracted `name` (Cargo `id`) of the bloons fixture | `test_split_bloon_name_fixture_names_resolve` |
| T16 | Hypothesis | for any base from `{"Red","Blue","Moab","Ddt"}` and any flag triple, the name `base + Regrow? + Camo? + Fortified?` splits back to that triple | `test_split_bloon_name_round_trip` |
