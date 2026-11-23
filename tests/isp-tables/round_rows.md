# Round data: `fetch_roundset` and `extract_round_rows`

## Rules for these tests

- Module constants: `MAX_ROUND = 100` and `DEFAULT_ROUNDSET = "DefaultRoundSet"` in `btd6/etl/fetch.py`; `extract_round_rows` lives in `btd6/etl/extract.py`.
- Wiki page title is `JSON:Bloons TD 6/Rounds/<name>`. Its content is a JSON string: `{"rounds": [{"bloonGroups": [{"bloon", "count", "start", "duration"}]}]}`.
- The round number is the list index plus 1; the wiki gives no explicit round field.
- One output row per bloon group: `{"round", "group_index", "bloon", "count", "start", "duration"}`. `group_index` is the 0-based position within the round, because a bloon type can repeat in one round.
- Rows are ordered by round, then `group_index`. Rounds past `max_round` are dropped.
- Network is faked (monkeypatch `requests.get` as in `tests/test_fetch_tower_module.py`); never hit the wiki.

---

## fetch_roundset

```python
def fetch_roundset(name: str = DEFAULT_ROUNDSET) -> dict[str, Any]
```

Fetches `JSON:Bloons TD 6/Rounds/<name>` and returns the decoded roundset (double decode: API envelope, then the content string).

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`name`|A) Roundset name|A1: Default|(omitted)|
|||A2: Custom|`"AlternateRoundSet"`|
|API response|B) Page state|B1: Page exists|envelope with `revisions[0].slots.main.content` = `'{"rounds": []}'`|
|||B2: Page missing|envelope page has `"missing": true`|
|||B3: HTTP error|`raise_for_status` raises `requests.HTTPError`|

Base case: A1, B1

### BCC

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | returns `{"rounds": []}`; request `titles` is `"JSON:Bloons TD 6/Rounds/DefaultRoundSet"` | `test_fetch_roundset_default` |
| T2 | A2 | B1 | request `titles` is `"JSON:Bloons TD 6/Rounds/AlternateRoundSet"` | `test_fetch_roundset_custom_name` |
| T3 | A1 | B2 | raises `ValueError` with message `Roundset "DefaultRoundSet" not found on the wiki` | `test_fetch_roundset_missing_page` |
| T4 | A1 | B3 | raises `requests.HTTPError` | `test_fetch_roundset_http_error` |

---

## extract_round_rows

```python
def extract_round_rows(roundset: dict[str, Any], max_round: int = MAX_ROUND) -> list[dict[str, Any]]
```

Flattens a roundset into one row per bloon group for rounds 1 through `max_round`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`roundset`|A) Rounds available vs `max_round`|A1: Fewer rounds than `max_round`|3 rounds, `max_round` = 100|
|||A2: Exactly `max_round` rounds|100 rounds|
|||A3: More rounds than `max_round`|101 rounds|
|||A4: No rounds|`{"rounds": []}`|
|`roundset` (round contents)|B) Groups in a round|B1: One group|`[{"bloon": "Red", "count": 20, "start": 0, "duration": 17.5125}]`|
|||B2: Several different bloons|Red, then Blue|
|||B3: Same bloon repeated|Red, Blue, Red (as the wiki's round 3)|
|||B4: No groups|`{"bloonGroups": []}`|
|`max_round`|C) Validity|C1: At least 1|`100`|
|||C2: Zero|`0`|
|||C3: Negative|`-1`|
|`roundset` (shape)|D) Top-level key|D1: Has `rounds` list|`{"rounds": [...]}`|
|||D2: No `rounds` key|`{}`|

Base case: A1, B2, C1, D1

### BCC

Base fixture: `{"rounds": [round1 (one Red group), round2 (Red then Blue), round3 (Red, Blue, Red)]}` with `max_round` = 100.

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B2 | C1 | D1 | rows for rounds 1-3; round 2 has `group_index` 0 = Red and 1 = Blue; every row has exactly the keys `round, group_index, bloon, count, start, duration` | `test_extract_round_rows_base` |
| T2 | A2 | B2 | C1 | D1 | `len(rows)` equals the group total; last row's `round` is `100` | `test_extract_round_rows_exactly_max` |
| T3 | A3 | B2 | C1 | D1 | no row has `round` above `100`; round 101 absent | `test_extract_round_rows_truncates_past_max` |
| T4 | A4 | B2 | C1 | D1 | returns `[]` | `test_extract_round_rows_no_rounds` |
| T5 | A1 | B1 | C1 | D1 | one row for round 1 with `group_index` 0 and `duration` 17.5125 | `test_extract_round_rows_single_group` |
| T6 | A1 | B3 | C1 | D1 | round 3 rows have `group_index` 0, 1, 2 and bloons Red, Blue, Red; none merged | `test_extract_round_rows_repeated_bloon` |
| T7 | A1 | B4 | C1 | D1 | the empty round contributes no rows; later rounds keep their number (round 3 stays `3`) | `test_extract_round_rows_empty_round_keeps_numbering` |
| T8 | A1 | B2 | C2 | D1 | raises `ValueError`: `max_round must be at least 1, got 0` | `test_extract_round_rows_invalid_max_round` (parametrized, 0) |
| T9 | A1 | B2 | C3 | D1 | raises `ValueError`: `max_round must be at least 1, got -1` | `test_extract_round_rows_invalid_max_round` (parametrized, -1) |
| T10 | A1 | B2 | C1 | D2 | raises `ValueError`: `roundset has no "rounds" list` | `test_extract_round_rows_missing_rounds_key` |

Extra tests, not BCC: `max_round` omitted equals `max_round=100`; a Hypothesis property that for any `max_round` in 1-150 the highest `round` is at most `max_round` and rows are sorted by `(round, group_index)`.
