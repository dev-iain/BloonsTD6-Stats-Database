# Round loader: `load_bloons` and `load_rounds` in `btd6/db/round_loader.py`

## Rules for these tests

- Both functions mirror `btd6/db/loader.py::load_tower`: one transaction (`with connection:`), parameterized SQL, any failure rolls back everything and re-raises.
- Tables come from migration `003_rounds.sql` (numbered 003 because `002_costs` exists): `bloons(id, name UNIQUE, health, layers, rbe, is_moab CHECK IN (0,1), speed)`, `rounds(round PK CHECK >= 1)`, `round_groups(id, round FK, group_index, bloon_id FK, is_camo, is_regrow, is_fortified, count CHECK > 0, start (NOT NULL, may be negative), duration CHECK >= 0, UNIQUE(round, group_index))`. Tests use a migrated `:memory:` connection with foreign keys on.
- `load_bloons(connection, rows) -> int`: `rows` is the output of `extract_bloon_rows`. It upserts on `name` and keeps the `id` of bloons that already exist (because `round_groups.bloon_id` references them, a delete-and-reinsert would break the foreign key). Bloons in the database but absent from `rows` are deleted only if no `round_groups` row references them. Returns the number of bloon rows written (`len(rows)`). `is_moab` is stored as 0 or 1.
- `load_rounds(connection, rows, bloon_ids) -> int`: `rows` is the output of `extract_round_rows`; `bloon_ids` is `dict[str, int]` from base bloon name to `bloons.id`. It deletes every `round_groups` and `rounds` row, then inserts one `rounds` row per distinct round number and one `round_groups` row per input row. The `bloon` text is split with `split_bloon_name`; the base name is looked up in `bloon_ids`; the three flags are stored as 0/1. Returns the number of groups written.
- An unknown base bloon raises `ValueError('Unknown bloon "<name>" in round <n>')`. A row that breaks a `CHECK` or the `UNIQUE (round, group_index)` raises `sqlite3.IntegrityError`. Both roll back, so rows loaded earlier survive.
- Open decision: an empty `rows` list for `load_rounds` clears the round tables (a roundset with zero rounds is a valid, if odd, replacement). Confirm before writing the test.

Shared fixtures:

- `BLOON_ROWS = [Red, Blue, Moab]` as typed rows (`Red`: health 1, layers 1, rbe 1, `is_moab` False, speed 1.0; `Blue`: health 1, layers 2, rbe 2; `Moab`: health 200, layers 0, rbe 616, `is_moab` True, speed 1.0).
- `ROUND_ROWS`: round 1 = `Red` x20; round 2 = `Red` x35; round 3 = `Red` x5, `BlueCamo` x3, `Red` x2 (group indexes 0, 1, 2). That is 3 rounds and 5 groups.

---

## load_bloons

```python
def load_bloons(connection: sqlite3.Connection, rows: list[dict[str, Any]]) -> int
```

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`rows`|A) Size|A1: Several **(Base)**|`BLOON_ROWS` (3 rows)|
|||A2: Empty|`[]`|
|||A3: One|`[Red]`|
|`connection` (state)|B) Bloons already stored|B1: None **(Base)**|empty `bloons` table|
|||B2: Same rows|`load_bloons(connection, BLOON_ROWS)` already called|
|||B3: Same names, different values|`Red` stored with `rbe` 99|
|||B4: A bloon not in the new rows, unreferenced|`Zomg` stored, no round groups|
|||B5: A bloon not in the new rows, referenced|`Zomg` stored and used by a `round_groups` row|
|`rows` (values)|C) Value kinds|C1: Typed values **(Base)**|`Moab` has `is_moab` True|
|||C2: NULL stats|`Red` with `health` None and `speed` None|
|||C3: Invalid `is_moab`|`{"name": "Red", ..., "is_moab": 2}`|

Base case: A1, B1, C1

Excluded or reduced combinations: A2 with B2 to B5 is the "empty list clears" question and is a non-BCC test; C3 fails the `CHECK`, so it is combined only with B1 for BCC and with B2 as a rollback extra.

### BCC

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | returns `3`; `SELECT COUNT(*) FROM bloons` is `3`; `Moab` row has `is_moab` `1`, `Red` has `0` | `test_load_bloons_base` |
| T2 | A2 | B1 | C1 | returns `0`; `bloons` stays empty | `test_load_bloons_empty` |
| T3 | A3 | B1 | C1 | returns `1`; one row, name `Red` | `test_load_bloons_single` |
| T4 | A1 | B2 | C1 | returns `3`; still 3 rows; every `id` equals its value after the first load | `test_load_bloons_idempotent_keeps_ids` |
| T5 | A1 | B3 | C1 | `Red.rbe` is `1` (was 99); `Red.id` unchanged; 3 rows | `test_load_bloons_updates_changed_values` |
| T6 | A1 | B4 | C1 | `Zomg` row deleted; 3 rows remain | `test_load_bloons_removes_unreferenced_bloon` |
| T7 | A1 | B5 | C1 | raises `sqlite3.IntegrityError`; `Zomg` and the previously stored rows are untouched | `test_load_bloons_keeps_referenced_bloon_on_failure` |
| T8 | A1 | B1 | C2 | returns `3`; `Red` row has `health` NULL and `speed` NULL | `test_load_bloons_null_stats` |
| T9 | A1 | B1 | C3 | raises `sqlite3.IntegrityError`; `bloons` is empty (the valid `Blue` and `Moab` rows were rolled back) | `test_load_bloons_invalid_is_moab_rolls_back` |

Extra tests, not BCC:

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T10 | failure with existing data (B2 and C3) | the second call raises; the first load's 3 rows are unchanged | `test_load_bloons_failure_leaves_previous_rows` |
| T11 | Hypothesis | loading any list of unique-name rows twice leaves the same row set and the same ids | `test_load_bloons_reload_is_idempotent` |
| T12 | Injection | a bloon name of `"Red'; DROP TABLE bloons;--"` is stored as plain text | `test_load_bloons_parameterized_sql` |

---

## load_rounds

```python
def load_rounds(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
    bloon_ids: dict[str, int],
) -> int
```

### ISP

`bloon_ids` is `{"Red": id_red, "Blue": id_blue, "Moab": id_moab}` read back after `load_bloons(connection, BLOON_ROWS)`.

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`rows`|A) Size|A1: Several rounds **(Base)**|`ROUND_ROWS` (3 rounds, 5 groups)|
|||A2: Empty|`[]`|
|||A3: Full roundset|100 rounds from the `extract_round_rows` output of a generated roundset, 1 `Red` group each|
|`connection` (state)|B) Round data already stored|B1: None **(Base)**|empty `rounds` and `round_groups`|
|||B2: Same rows|`load_rounds(connection, ROUND_ROWS, ids)` already called|
|||B3: Longer old roundset|5 rounds already stored; new `rows` has 3|
|||B4: Same round numbers, different groups|round 1 stored as `Blue` x1|
|`rows` (bloon names)|C) Bloon name|C1: Known base name **(Base)**|`"Red"`|
|||C2: Known name with modifiers|`"BlueCamo"` (base `Blue`, `is_camo` 1)|
|||C3: Unknown base|`"Zomg"` not in `bloon_ids`|
|`rows` (group values)|D) Group validity|D1: Valid **(Base)**|`count` 20, `start` 0, `duration` 17.5|
|||D2: `count` is zero|`count` 0|
|||D3: `count` is negative|`count` -1|
|||D4: Repeated `(round, group_index)`|two rows with `round` 1, `group_index` 0|
|||D5: Round number below 1|`round` 0|
|||D6: Negative `start` (accepted)|`start` -0.15, as in wiki round 86 group 0|

Base case: A1, B1, C1, D1

Excluded or reduced combinations: C2 is already part of `ROUND_ROWS` (round 3), so the base also contains one modified bloon; T6 checks its flags. C3 and D2 to D5 each fail on the first bad row, so they are checked for rollback with B1 in BCC and with stored data (B2) in the combined extra test T13, which is not a BCC test.

### BCC

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | returns `5`; `rounds` has 3 rows (1, 2, 3); `round_groups` has 5 rows; round 1 group 0 has `bloon_id` of `Red`, `count` 20, `is_camo` 0 | `test_load_rounds_base` |
| T2 | A2 | B1 | C1 | D1 | returns `0`; both tables empty | `test_load_rounds_empty` |
| T3 | A3 | B1 | C1 | D1 | returns `100`; `rounds` has 100 rows; `MAX(round)` is `100` | `test_load_rounds_full_roundset` |
| T4 | A1 | B2 | C1 | D1 | returns `5`; counts still 3 and 5; the rows equal those after the first load (no duplicates) | `test_load_rounds_idempotent` |
| T5 | A1 | B3 | C1 | D1 | returns `5`; `rounds` has exactly rounds 1-3 (rounds 4 and 5 and their groups are gone) | `test_load_rounds_shorter_roundset_removes_old_rows` |
| T6 | A1 | B1 | C2 | D1 | round 3 group 1 has `bloon_id` of `Blue`, `is_camo` 1, `is_regrow` 0, `is_fortified` 0 | `test_load_rounds_modifier_flags` |
| T7 | A1 | B4 | C1 | D1 | round 1 now has the new groups only (20 `Red`); the old `Blue` x1 group is gone; group count 5 | `test_load_rounds_replaces_changed_groups` |
| T8 | A1 | B1 | C3 | D1 | raises `ValueError('Unknown bloon "Zomg" in round 3')`; `rounds` and `round_groups` empty | `test_load_rounds_unknown_bloon_rolls_back` |
| T9 | A1 | B1 | C1 | D2 | raises `sqlite3.IntegrityError`; both tables empty | `test_load_rounds_zero_count_rolls_back` |
| T10 | A1 | B1 | C1 | D3 | raises `sqlite3.IntegrityError`; both tables empty | `test_load_rounds_negative_count_rolls_back` |
| T11 | A1 | B1 | C1 | D4 | raises `sqlite3.IntegrityError` (UNIQUE `round, group_index`); both tables empty | `test_load_rounds_duplicate_group_rolls_back` |
| T12 | A1 | B1 | C1 | D5 | raises `sqlite3.IntegrityError` (CHECK `round >= 1`); both tables empty | `test_load_rounds_round_zero_rolls_back` |

Extra tests, not BCC:

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T13 | B2 with C3 and with D2 (parametrized) | the failing second call raises; the 3 rounds and 5 groups from the first load are unchanged | `test_load_rounds_failure_leaves_old_rows` |
| T14 | foreign keys | a `bloon_ids` value that is not in `bloons` (e.g. 9999) raises `sqlite3.IntegrityError`; tables empty | `test_load_rounds_bloon_id_must_exist` |
| T15 | order | `SELECT ... ORDER BY round, group_index` equals `ROUND_ROWS` order for round 3 (`Red`, `Blue`, `Red`) | `test_load_rounds_keeps_group_order` |
| T16 | round trip | rows loaded from `tests/fixtures/default_roundset_first10_rows.csv` and read back with `round_groups` joined to `bloons` equal that CSV (modifiers re-joined into the name) | `test_load_rounds_round_trip_fixture` |
| T17 | Hypothesis | loading the same generated valid rows twice gives the same row count; the group count equals `len(rows)` | `test_load_rounds_reload_is_idempotent` |
