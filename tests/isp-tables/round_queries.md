# Round queries: `get_round`, `get_round_summary` and the `rounds` CLI

## Rules for these tests

- `get_round`, `get_round_summary`, `RoundGroup` and `RoundSummary` live in `btd6/rounds.py`. SQL is parameterized.
- `RoundGroup` (frozen dataclass) fields: `group_index`, `bloon` (base name), `is_camo`, `is_regrow`, `is_fortified`, `count`, `start`, `duration`, `rbe`, `is_moab`. `get_round` returns them ordered by `group_index`.
- `RoundSummary` fields: `round`, `total_bloons` (sum of `count`), `total_rbe` (sum of `count * rbe` using the base bloon's `rbe`; fortified health is not applied, to be documented in `docs/queries.md`), `has_moab` (any group with `is_moab`), `has_camo` (any `is_camo`), `has_lead` (any base bloon `Lead`), `has_ceramic` (any base bloon `Ceramic`).
- Errors: a round below 1 or above the highest loaded round raises `ValueError` (`Round <n> is not loaded; loaded rounds are 1-<max>`; when the table is empty: `No round data loaded`). A value that is not an `int`, including `bool`, raises `TypeError` (a `bool` is rejected on purpose: `True` would silently mean round 1). Both rules are open decisions to confirm.
- Fixture `ROUNDS_DB` (migrated `:memory:`; built with the loaders from `tests/factories.py` rows; a hand-made fixture, not wiki data). Bloons: `Red` rbe 1, `Blue` rbe 2, `Pink` rbe 5, `Lead` rbe 23, `Ceramic` rbe 104, `Moab` rbe 616 (`is_moab` 1). Rounds 1-40 are loaded. Every round not listed is one group `Red` x1.

| Round | Groups (`group_index` order) |
|---|---|
| 1 | `Red` x20 |
| 3 | `Red` x5, `Blue` x3, `Red` x2 |
| 24 | `BlueCamo` x10 |
| 27 | `Lead` x6 |
| 35 | `Ceramic` x3 |
| 40 | `Pink` x20, `Moab` x1 |

---

## get_round

```python
def get_round(connection: sqlite3.Connection, round_number: int) -> list[RoundGroup]
```

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`round_number`|A) Value|A1: First round **(Base)**|`1`|
|||A2: Last loaded round|`40`|
|||A3: Zero|`0`|
|||A4: Negative|`-1`|
|||A5: One past the loaded data|`41`|
|||A6: Past the game's 100 rounds|`101`|
|`round_number`|B) Type|B1: `int` **(Base)**|`1`|
|||B2: `str`|`"1"`|
|||B3: `float`|`1.0`|
|||B4: `bool`|`True`|
|||B5: `None`|`None`|
|`connection` (state)|C) Data loaded|C1: Rounds 1-40 **(Base)**|`ROUNDS_DB`|
|||C2: Migrated, no round rows|`:memory:` after `apply_migrations` only|

Base case: A1, B1, C1

Excluded or reduced combinations: A and B both describe the argument, so B2 to B5 replace the value (their oracle does not depend on A); A3 to A6 are combined with B1 only.

### BCC

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | returns one `RoundGroup`: `group_index` 0, `bloon` `"Red"`, `count` 20, all three flags False, `is_moab` False, `rbe` 1 | `test_get_round_first_round` |
| T2 | A2 | B1 | C1 | returns two groups in order: `Pink` x20 then `Moab` x1; the second has `is_moab` True and `rbe` 616 | `test_get_round_last_loaded_round` |
| T3 | A3 | B1 | C1 | raises `ValueError` mentioning round 0 | `test_get_round_zero` |
| T4 | A4 | B1 | C1 | raises `ValueError` mentioning round -1 | `test_get_round_negative` |
| T5 | A5 | B1 | C1 | raises `ValueError`: `Round 41 is not loaded; loaded rounds are 1-40` | `test_get_round_beyond_loaded_data` |
| T6 | A6 | B1 | C1 | raises `ValueError` mentioning round 101 | `test_get_round_past_max_round` |
| T7 | A1 | B2 | C1 | raises `TypeError` | `test_get_round_string_argument` |
| T8 | A1 | B3 | C1 | raises `TypeError` | `test_get_round_float_argument` |
| T9 | A1 | B4 | C1 | raises `TypeError` (not round 1) | `test_get_round_bool_argument` |
| T10 | A1 | B5 | C1 | raises `TypeError` | `test_get_round_none_argument` |
| T11 | A1 | B1 | C2 | raises `ValueError`: `No round data loaded` | `test_get_round_no_data_loaded` |

Extra tests, not BCC:

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T12 | repeated bloon, order | round 3 returns `Red` x5, `Blue` x3, `Red` x2 with `group_index` 0, 1, 2 (no merging) | `test_get_round_repeated_bloon_keeps_order` |
| T13 | modifiers | round 24 returns one group `bloon` `"Blue"`, `is_camo` True, `is_regrow` False | `test_get_round_modifier_flags` |
| T14 | immutability | assigning to a `RoundGroup` field raises `FrozenInstanceError` | `test_round_group_is_frozen` |
| T15 | Hypothesis | for every round 1-40 the result is non-empty and sorted by `group_index` | `test_get_round_sorted_for_every_round` |

---

## get_round_summary

```python
def get_round_summary(connection: sqlite3.Connection, round_number: int) -> RoundSummary
```

Aggregates one round. Argument validation is identical to `get_round` (same helper), so only the representative invalid values are repeated here.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`round_number`|A) Validity|A1: Loaded round **(Base)**|a loaded round, chosen by B|
|||A2: Zero|`0`|
|||A3: Beyond loaded data|`41`|
|||A4: Not an `int`|`True`|
|round contents|B) Special bloons in the round|B1: None of the flags **(Base)**|round 1 (`Red` x20)|
|||B2: A MOAB-class bloon|round 40 (`Pink` x20, `Moab` x1)|
|||B3: Camo group|round 24 (`BlueCamo` x10)|
|||B4: Lead|round 27 (`Lead` x6)|
|||B5: Ceramic|round 35 (`Ceramic` x3)|
|||B6: Several groups of one bloon|round 3 (`Red`, `Blue`, `Red`)|

Base case: A1, B1

Excluded or reduced combinations: A2 to A4 raise before any aggregation, so B does not apply; they use round 1 as the argument where a value is needed. A flag shared by two bloons (lead and ceramic in one round) is a non-BCC test.

### BCC

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | `RoundSummary(round=1, total_bloons=20, total_rbe=20, has_moab=False, has_camo=False, has_lead=False, has_ceramic=False)` | `test_get_round_summary_first_round` |
| T2 | A1 | B2 | `total_bloons` 21, `total_rbe` 716 (20x5 + 616), `has_moab` True, other flags False | `test_get_round_summary_moab_round` |
| T3 | A1 | B3 | `total_bloons` 10, `total_rbe` 20, `has_camo` True, `has_moab` False | `test_get_round_summary_camo_round` |
| T4 | A1 | B4 | `total_bloons` 6, `total_rbe` 138, `has_lead` True, `has_ceramic` False | `test_get_round_summary_lead_round` |
| T5 | A1 | B5 | `total_bloons` 3, `total_rbe` 312, `has_ceramic` True, `has_lead` False | `test_get_round_summary_ceramic_round` |
| T6 | A1 | B6 | `total_bloons` 10, `total_rbe` 13 (5 + 6 + 2); all flags False | `test_get_round_summary_repeated_bloon_round` |
| T7 | A2 | B1 | raises `ValueError` mentioning round 0 | `test_get_round_summary_zero` |
| T8 | A3 | B1 | raises `ValueError`: `Round 41 is not loaded; loaded rounds are 1-40` | `test_get_round_summary_beyond_loaded_data` |
| T9 | A4 | B1 | raises `TypeError` | `test_get_round_summary_bool_argument` |

Extra tests, not BCC: a round holding both `Lead` and `Ceramic` sets both flags (`test_get_round_summary_lead_and_ceramic`); `total_bloons` and `total_rbe` equal the sums over `get_round` for every round (Hypothesis, `test_get_round_summary_matches_get_round`); a camo `Lead` group (`LeadCamo`) sets `has_lead` and `has_camo` (the flag follows the base name).

---

## main: `rounds` (#87)

```python
def main(argv: list[str] | None = None) -> int
```

Parses `argv` for the `rounds` subcommand, calls `get_round` for one round (`--round N`) or each round of a range (`--from A --to B`, inclusive) and prints a pandas table with columns `round`, `bloon`, `count`, `camo`, `regrow`, `fortified`, `start`, `duration`, `rbe`, one row per group, ordered by round then `group_index`. It follows the CLI rules in `tests/isp-tables/cli.md` (errors on stderr as one line, exit 2 for value errors, exit 1 for a missing database).

Rules for these tests:
- Tests do not pin number formatting. They parse each data line and compare against `get_round` on the same database.
- `--round` and the pair `--from`/`--to` are mutually exclusive; one of them is required; `--from` and `--to` come together. Argparse-level errors check the last stderr line and `SystemExit.code == 2`; `ValueError` from the query layer returns `2` with one stderr line.
- Fixture: `ROUNDS_DB` from above copied to `tmp_path / "btd6.db"`.

Base input: `main(["--db", DB, "rounds", "--round", "1"])`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`argv` (selection)|A) Which selection options|A1: `--round` only **(Base)**|`"--round", "1"`|
|||A2: `--from` and `--to`|`"--from", "1", "--to", "3"`|
|||A3: Neither|`"rounds"` alone|
|||A4: `--round` with `--from`/`--to`|`"--round", "1", "--from", "1", "--to", "3"`|
|||A5: `--from` without `--to`|`"--from", "1"`|
|`--round` value|B) Round number|B1: Loaded **(Base)**|`1`|
|||B2: Zero|`0`|
|||B3: Beyond loaded data|`41`|
|||B4: Not an integer|`"abc"`|
|`--db` (state: file)|C) State before the call|C1: Loaded **(Base)**|`ROUNDS_DB` file|
|||C2: Missing|`tmp_path / "missing.db"`|
|||C3: Schema present, no round data|migrated file with empty round tables|

Base case: A1, B1, C1

Excluded or reduced combinations: B applies to `--round`, so it is varied only with A1. Range-specific edges (reversed range, equal ends, range reaching past the data) are extra tests.

### BCC

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | returns `0`; stdout has a header and one data row: round 1, `Red`, count 20; stderr empty | `test_main_rounds_single_round` |
| T2 | A2 | B1 | C1 | returns `0`; data rows are rounds 1, 2, then 3 (`Red` x5, `Blue` x3, `Red` x2 in group order), 5 rows in total | `test_main_rounds_range` |
| T3 | A3 | B1 | C1 | `SystemExit.code == 2`; last stderr line `btd6 rounds: error: one of --round or --from/--to is required` | `test_main_rounds_no_selection` |
| T4 | A4 | B1 | C1 | `SystemExit.code == 2`; last stderr line `btd6 rounds: error: --round cannot be combined with --from/--to` | `test_main_rounds_round_and_range` |
| T5 | A5 | B1 | C1 | `SystemExit.code == 2`; last stderr line `btd6 rounds: error: --from and --to must be given together` | `test_main_rounds_from_without_to` |
| T6 | A1 | B2 | C1 | returns `2`; stdout empty; stderr one line mentioning round 0 | `test_main_rounds_zero` |
| T7 | A1 | B3 | C1 | returns `2`; stderr `Round 41 is not loaded; loaded rounds are 1-40` | `test_main_rounds_beyond_loaded_data` |
| T8 | A1 | B4 | C1 | `SystemExit.code == 2`; last stderr line starts `btd6 rounds: error: argument --round: invalid int value: 'abc'` | `test_main_rounds_non_integer` |
| T9 | A1 | B1 | C2 | returns `1`; stderr `Database not found at <path>. Run "python -m btd6 load" first.` | `test_main_rounds_database_missing` |
| T10 | A1 | B1 | C3 | returns `1`; stdout empty; stderr `No round data loaded. Run "python -m btd6 load" first.` | `test_main_rounds_no_round_data` |

Extra tests, not BCC:

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T11 | reversed range (`--from 3 --to 1`) | returns `2`; stderr `--from must not be greater than --to` | `test_main_rounds_reversed_range` |
| T12 | equal ends (`--from 3 --to 3`) | same rows as `--round 3` | `test_main_rounds_range_of_one_round` |
| T13 | range past the data (`--from 39 --to 41`) | returns `2`; stderr names round 41; stdout empty (no partial table) | `test_main_rounds_range_past_loaded_data` |
| T14 | modifiers in output | `--round 24` row shows `camo` true and `regrow` false | `test_main_rounds_shows_modifier_flags` |
| T15 | help | `btd6 rounds --help` lists `--round`, `--from`, `--to` | `test_main_rounds_help_lists_options` |
