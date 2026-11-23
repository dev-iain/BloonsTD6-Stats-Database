# Income: pop cash, round multiplier, round and cumulative income

## Rules for these tests

- Spec: `docs/income.md`. Oracle for whole rounds: `tests/fixtures/wiki_round_cash.csv` (columns `round, pop_cash, end_bonus`, rounds 1-100). Sums over that CSV: rounds 1-5 = 735, rounds 1-40 = 16856, rounds 1-100 = 178994.
- `bloon_pop_cash` and `round_multiplier` live in `btd6/income.py` (#92). `fetch_income_set` lives in `btd6/etl/fetch.py`, `extract_income_thresholds` in `btd6/etl/extract.py`, `load_income` in `btd6/db/` (#91).
- DB tests use SQLite `:memory:`. Two fixtures: `income_db` (full: income tables loaded from the DefaultIncomeSet thresholds plus rounds 1-100 and bloons loaded) and `short_income_db` (rounds 1-5 only, same thresholds). Both built with factory_boy factories; network is faked, never the wiki.
- Children fixture for `bloon_pop_cash` (wiki `parent of`): `Red: []`, `Blue: [Red x1]`, `Green: [Blue x1]`, `Yellow: [Green x1]`, `Pink: [Yellow x1]`, `Black: [Pink x2]`, `White: [Pink x2]`, `Lead: [Black x2]`, `Zebra: [Black x1, White x1]`, `Rainbow: [Zebra x2]`, `Ceramic: [Rainbow x2]`, `MOAB: [Ceramic x4]`, `BFB: [MOAB x4]`, `ZOMG: [BFB x4]`, `DDT: [Ceramic x4]`, `BAD: [ZOMG x2, DDT x3]`.
- Expected pop cash, normal / super: Red 1/1, Black 11/6, Lead 23/7, Zebra 23/7, Rainbow 47/8, Ceramic 95/95, MOAB 381/381, DDT 381/381, BFB 1525/1525, ZOMG 6101/6101, BAD 13346/13346.

---

## bloon_pop_cash

```python
def bloon_pop_cash(name: str, children: Mapping[str, list[tuple[str, int]]], moab_names: frozenset[str], super_ceramic: bool) -> int
```

Pure and recursive (spec section 1): own cash 1 (87 for Ceramic when `super_ceramic`) plus `count x bloon_pop_cash(child)` per child. When `super_ceramic` and the bloon is not in `moab_names`, only the first child is released, with count 1 (Zebra releases only Black). MOAB-class bloons are unchanged. Design note: the spec needs to know which bloons are MOAB-class, so the signature adds `moab_names: frozenset[str]` (here `{"MOAB","BFB","ZOMG","DDT","BAD"}`).

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`name`|A) Kind of bloon|A1: Leaf, no children|`"Red"`|
|||A2: Non-MOAB, first child has count above 1|`"Lead"`|
|||A3: Non-MOAB, several different children|`"Zebra"`|
|||A4: Ceramic|`"Ceramic"`|
|||A5: MOAB-class, one child type|`"MOAB"`|
|||A6: MOAB-class, mixed child types|`"BAD"`|
|`super_ceramic`|B) Round regime|B1: Rounds 1-80 (`False`)|`False`|
|||B2: Rounds 81+ (`True`)|`True`|

Base case: A2, B1

### BCC

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A2 | B1 | `bloon_pop_cash("Lead", ...)` returns `23` (1 + 2 x 11) | `test_bloon_pop_cash_base` |
| T2 | A1 | B1 | returns `1` | `test_bloon_pop_cash_leaf` |
| T3 | A3 | B1 | returns `23` (1 + 11 + 11) | `test_bloon_pop_cash_several_children` |
| T4 | A4 | B1 | returns `95` | `test_bloon_pop_cash_ceramic` |
| T5 | A5 | B1 | returns `381` | `test_bloon_pop_cash_moab` |
| T6 | A6 | B1 | returns `13346` (1 + 2 x 6101 + 3 x 381) | `test_bloon_pop_cash_bad` |
| T7 | A2 | B2 | returns `7` (Lead, then one Black, Pink, Yellow, Green, Blue, Red) | `test_bloon_pop_cash_super_first_child_only` |

Extra tests, not BCC (combinations of the two characteristics):
- A1, B2: Red returns `1`.
- A3, B2: Zebra returns `7` (only Black released, never White).
- A4, B2: Ceramic returns `95` (87 + Rainbow chain 8).
- A5, B2 and A6, B2: MOAB `381`, BAD `13346` (unchanged).
- Rainbow is `47` with `False` and `8` with `True`.
- Parametrize the whole expected-values list in the rules section as one table test, `test_bloon_pop_cash_known_values`.

Hypothesis properties: for a generated acyclic children map, `bloon_pop_cash(name, ...) >= 1`; with `super_ceramic=False` the result equals `1 + sum(count * bloon_pop_cash(child))`; with `super_ceramic=True` and no Ceramic in the tree, the result is at most the `False` result.

---

## round_multiplier

```python
def round_multiplier(connection: sqlite3.Connection, round_number: int) -> float
```

Looks up the first `income_thresholds` row with `threshold >= round_number`; above the last threshold it returns `income_settings.final_multiplier`. Thresholds loaded: 50 -> 1, 60 -> 0.5, 85 -> 0.2, 100 -> 0.1, 120 -> 0.05, 140 -> 0.04, final 0.02. Rounds below 1 and a database with no thresholds raise `ValueError`. It needs no round data.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`round_number`|A) Position relative to thresholds|A1: Zero|`0`|
|||A2: Negative|`-1`|
|||A3: First round|`1`|
|||A4: Last of first band (equals threshold)|`50`|
|||A5: First of second band|`51`|
|||A6: Equals threshold 60|`60`|
|||A7: Just above threshold 60|`61`|
|||A8: Equals threshold 85|`85`|
|||A9: Just above threshold 85|`86`|
|||A10: Equals threshold 100|`100`|
|||A11: Just above threshold 100|`101`|
|||A12: Equals threshold 120|`120`|
|||A13: Just above threshold 120|`121`|
|||A14: Equals last threshold 140|`140`|
|||A15: Above last threshold (final multiplier)|`141`|
|`connection` (state)|B) Thresholds loaded|B1: Loaded|7-band `DefaultIncomeSet` data|
|||B2: Not loaded|empty `income_thresholds`|

Base case: A3, B1

### BCC

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A3 | B1 | returns `1.0` | `test_round_multiplier_base` |
| T2 | A1 | B1 | raises `ValueError` | `test_round_multiplier_invalid_round` (parametrized, 0) |
| T3 | A2 | B1 | raises `ValueError` | `test_round_multiplier_invalid_round` (parametrized, -1) |
| T4 | A4 | B1 | returns `1.0` | `test_round_multiplier_boundaries` (parametrized, 50) |
| T5 | A5 | B1 | returns `0.5` | `test_round_multiplier_boundaries` (51) |
| T6 | A6 | B1 | returns `0.5` | `test_round_multiplier_boundaries` (60) |
| T7 | A7 | B1 | returns `0.2` | `test_round_multiplier_boundaries` (61) |
| T8 | A8 | B1 | returns `0.2` | `test_round_multiplier_boundaries` (85) |
| T9 | A9 | B1 | returns `0.1` | `test_round_multiplier_boundaries` (86) |
| T10 | A10 | B1 | returns `0.1` | `test_round_multiplier_boundaries` (100) |
| T11 | A11 | B1 | returns `0.05` | `test_round_multiplier_boundaries` (101) |
| T12 | A12 | B1 | returns `0.05` | `test_round_multiplier_boundaries` (120) |
| T13 | A13 | B1 | returns `0.04` | `test_round_multiplier_boundaries` (121) |
| T14 | A14 | B1 | returns `0.04` | `test_round_multiplier_boundaries` (140) |
| T15 | A15 | B1 | returns `0.02` | `test_round_multiplier_boundaries` (141) |
| T16 | A3 | B2 | raises `ValueError` (no thresholds loaded) | `test_round_multiplier_no_thresholds` |

Hypothesis property: the multiplier is non-increasing over rounds 1-500 and always one of `{1, 0.5, 0.2, 0.1, 0.05, 0.04, 0.02}`.

---

## round_income

```python
def round_income(connection: sqlite3.Connection, round_number: int) -> RoundIncome
```

Returns `RoundIncome(pop_cash, end_bonus, total)`: `pop_cash = round_multiplier x sum(count x pop_cash_for_round)` (uses `bloons.pop_cash` up to round 80, `bloons.pop_cash_super` from 81), `end_bonus = 100 + round` (never multiplied), `total = pop_cash + end_bonus`. Rounds below 1, above the last loaded round, or with no round data raise `ValueError`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`round_number`|A) Round|A1: First round, Red only|`1`|
|||A2: Single MOAB|`40`|
|||A3: Lead and Ceramic, multiplier 0.2|`63`|
|||A4: Last normal-cash round|`80`|
|||A5: First super-ceramic round|`81`|
|||A6: Last loaded round|`100`|
|||A7: Last loaded round + 1|`101`|
|||A8: Zero|`0`|
|||A9: Negative|`-1`|
|`connection` (state)|B) Round data|B1: Loaded (`income_db`)|rounds 1-100|
|||B2: Not loaded|empty `rounds` table|

Base case: A1, B1

### BCC

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | `RoundIncome(20.0, 101, 121.0)` | `test_round_income_base` |
| T2 | A2 | B1 | `RoundIncome(381.0, 140, 521.0)` | `test_round_income_known_rounds` (parametrized, 40) |
| T3 | A3 | B1 | `RoundIncome(2663.0, 163, 2826.0)` (75 x 23 + 122 x 95 = 13315, x 0.2) | `test_round_income_known_rounds` (63) |
| T4 | A4 | B1 | `RoundIncome(1220.2, 180, 1400.2)` (CSV round 80) | `test_round_income_known_rounds` (80) |
| T5 | A5 | B1 | `RoundIncome(5185.0, 181, 5366.0)` (CSV round 81; uses `pop_cash_super`) | `test_round_income_super_ceramic_switch` |
| T6 | A6 | B1 | `RoundIncome(1334.6, 200, 1534.6)` | `test_round_income_last_round` |
| T7 | A7 | B1 | raises `ValueError` | `test_round_income_invalid_round` (parametrized, 101) |
| T8 | A8 | B1 | raises `ValueError` | `test_round_income_invalid_round` (0) |
| T9 | A9 | B1 | raises `ValueError` | `test_round_income_invalid_round` (-1) |
| T10 | A1 | B2 | raises `ValueError` | `test_round_income_no_round_data` |

Extra tests, not BCC: rounds 2-5 return totals `137, 138, 175, 164`; on `short_income_db` round 5 is the last (`164.0`) and round 6 raises `ValueError`; every round 1-100 matches the CSV (`pop_cash` approx `pop_cash` column, `end_bonus` equal), as one parametrized test, `test_round_income_matches_wiki_csv`.

Hypothesis properties (`round_number` in 1-100): `end_bonus == 100 + round_number`; `total == pop_cash + end_bonus`; `pop_cash >= 0`.

---

## cumulative_income

```python
def cumulative_income(connection: sqlite3.Connection, up_to_round: int) -> float
```

Sum of `round_income(k).total` for `k = 1..up_to_round`. Starting cash ($650) is not included. Rounds below 1, above the last loaded round, or no round data raise `ValueError`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`up_to_round`|A) Round|A1: First round|`1`|
|||A2: Few rounds|`5`|
|||A3: Wiki reference round|`40`|
|||A4: Last loaded round|`100`|
|||A5: Last loaded round + 1|`101`|
|||A6: Zero|`0`|
|||A7: Negative|`-1`|
|`connection` (state)|B) Round data|B1: Loaded (`income_db`)|rounds 1-100|
|||B2: Not loaded|empty `rounds` table|

Base case: A2, B1

### BCC

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A2 | B1 | returns approx `735.0` (121 + 137 + 138 + 175 + 164) | `test_cumulative_income_base` |
| T2 | A1 | B1 | returns `121.0` | `test_cumulative_income_known_rounds` (parametrized, 1) |
| T3 | A3 | B1 | returns approx `16856.0` | `test_cumulative_income_known_rounds` (40) |
| T4 | A4 | B1 | returns approx `178994.0` (sum of CSV `pop_cash + end_bonus`) | `test_cumulative_income_last_round` |
| T5 | A5 | B1 | raises `ValueError` | `test_cumulative_income_invalid_round` (parametrized, 101) |
| T6 | A6 | B1 | raises `ValueError` | `test_cumulative_income_invalid_round` (0) |
| T7 | A7 | B1 | raises `ValueError` | `test_cumulative_income_invalid_round` (-1) |
| T8 | A2 | B2 | raises `ValueError` | `test_cumulative_income_no_round_data` |

Hypothesis properties (`n` in 2-100): `cumulative_income(n) - cumulative_income(n - 1)` approx `round_income(n).total`; strictly increasing in `n`; at least `sum(100 + k)`. Use `pytest.approx` for float comparisons.

---

## fetch_income_set (#91)

```python
def fetch_income_set(name: str = DEFAULT_INCOME_SET) -> dict[str, Any]
```

Fetches `JSON:Bloons TD 6/Rounds/<name>` and returns the decoded income set (same double decode as `fetch_roundset`). `DEFAULT_INCOME_SET = "DefaultIncomeSet"`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`name`|A) Income set name|A1: Default|(omitted)|
|||A2: Custom|`"AlternateIncomeSet"`|
|API response|B) Page state|B1: Page exists|content `'{"thresholds": {"items": []}, "finalMultiplier": 0.02}'`|
|||B2: Page missing|page has `"missing": true`|

Base case: A1, B1

### BCC

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | returns `{"thresholds": {"items": []}, "finalMultiplier": 0.02}`; request `titles` is `"JSON:Bloons TD 6/Rounds/DefaultIncomeSet"` | `test_fetch_income_set_default` |
| T2 | A2 | B1 | request `titles` is `"JSON:Bloons TD 6/Rounds/AlternateIncomeSet"` | `test_fetch_income_set_custom_name` |
| T3 | A1 | B2 | raises `ValueError`: `Income set "DefaultIncomeSet" not found on the wiki` | `test_fetch_income_set_missing_page` |

---

## extract_income_thresholds (#91)

```python
def extract_income_thresholds(income_set: dict[str, Any]) -> list[dict[str, Any]]
```

Returns one row `{"threshold": int, "multiplier": float}` per threshold, in the given order. `finalMultiplier` is not a row; it is read by the loader.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`income_set`|A) Thresholds|A1: Several|the 6 default thresholds (50/1 ... 140/0.04)|
|||A2: One|`[{"threshold": 50, "multiplier": 1}]`|
|||A3: Empty|`[]`|
|||A4: Key missing|`{}`|

Base case: A1

### BCC

| BCC Test | A | Oracle | Test Name |
|---|---|---|---|
| T1 | A1 | 6 rows; first `{"threshold": 50, "multiplier": 1}`, last `{"threshold": 140, "multiplier": 0.04}`, keys exactly `threshold, multiplier` | `test_extract_income_thresholds_base` |
| T2 | A2 | `[{"threshold": 50, "multiplier": 1}]` | `test_extract_income_thresholds_single` |
| T3 | A3 | returns `[]` | `test_extract_income_thresholds_empty` |
| T4 | A4 | raises `ValueError`: `income set has no "thresholds.items" list` | `test_extract_income_thresholds_missing_key` |

---

## load_income (#91)

```python
def load_income(connection: sqlite3.Connection, income_set: dict[str, Any]) -> None
```

Writes thresholds into `income_thresholds` and `finalMultiplier` into `income_settings`. Idempotent: reloading replaces, never duplicates.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`connection` (state)|A) Existing income data|A1: Empty tables|fresh `:memory:` DB|
|||A2: Same data already loaded|loaded once with the default set|
|||A3: Different data already loaded|loaded with 50 -> 1, final 0.02|
|`income_set`|B) Thresholds|B1: Default set|6 thresholds, final 0.02|
|||B2: Changed values|`{"thresholds": {"items": [{"threshold": 50, "multiplier": 0.9}]}, "finalMultiplier": 0.03}`|
|||B3: Empty thresholds|`{"thresholds": {"items": []}, "finalMultiplier": 0.02}`|

Base case: A1, B1

### BCC

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | 6 rows in `income_thresholds`; `round_multiplier(connection, 141)` is `0.02` | `test_load_income_first_load` |
| T2 | A2 | B1 | still 6 rows; contents identical to after first load | `test_load_income_reload_no_duplicates` |
| T3 | A3 | B2 | 1 row `(50, 0.9)`; `round_multiplier(connection, 51)` is `0.03` (old rows gone) | `test_load_income_changed_values_overwrite` |
| T4 | A1 | B3 | 0 threshold rows; `round_multiplier` raises `ValueError` | `test_load_income_empty_thresholds` |

Hypothesis property: loading the same generated income set N times (1-3) leaves the same table contents as loading it once.

---

## Ambiguities to settle before implementing

- Wiki income set JSON shape (verified live): `{"finalMultiplier": 0.02, "thresholds": {"items": [{"threshold": 50, "multiplier": 1}, ...]}}`.
- The spec does not say what happens for a bloon absent from `children`; tests assume it is a leaf (`children.get(name, [])`).
- `moab_names` is a parameter added by this table; `bloons` data may instead provide a MOAB flag.
- `extract_income_thresholds` and the missing-key `ValueError` messages are proposals.
