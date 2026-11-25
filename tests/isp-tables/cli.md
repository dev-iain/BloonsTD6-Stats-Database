# `main(argv: list[str] | None = None) -> int` in `btd6/cli.py`

## Rules for these tests

- Build the parser with `prog="btd6"` and subparsers with `dest="command"`.
- `--db` is global and comes before the subcommand: `btd6 --db PATH search ...`.
- Results go to stdout; errors go to stderr as one line, no traceback unless `--debug`.
- When the exit code is 0, stderr is empty. When it is not 0, stdout is empty, unless a case says otherwise.
- Cases marked `SystemExit.code` are argparse errors: wrap the call in `pytest.raises(SystemExit)` and check the **last** line of stderr (argparse prints `usage:` first). All other cases check the return value and the only line of stderr.
- "stdout is `format_results` of [paths]" means stdout equals `format_results(rows)` (#44) for those rows, in that order.
- `search` passes `category="Magic"` by default. `--can-pop X` means `can_pop_x=True`; `--cannot-pop X` means `can_pop_x=False`.

| Situation | Exit | stderr line |
|---|---|---|
| database file missing | 1 | `Database not found at <path>. Run "python -m btd6 load" first.` |
| negative threshold (query layer `ValueError`) | 2 | `min_pierce must be 0 or more, got -1.0` |
| unknown damage type (query layer `ValueError`) | 2 | `Unknown damage type "Bogus". Valid types: Acid, Cold, Energy, Explosion, Fire, Frigid, Glacier, Normal, Plasma, Sharp, Shatter, Unknown` |
| limit below 1 (query layer `ValueError`) | 2 | `limit must be at least 1, got 0` |
| same property in `--can-pop` and `--cannot-pop` | 2 | `--can-pop and --cannot-pop both list lead` |
| wiki unreachable during `load` | 1 | `Could not reach the wiki: <reason>` |
| one tower fails during `load` | 1 | `<Tower>: failed: <reason>` |
| any other exception | 1 | `Unexpected error: <message>` |

---

## main: dispatch and `search`

```python
def main(argv: list[str] | None = None) -> int
```

Parses `argv`, dispatches to the `search` or `load` subcommand, prints results to stdout and returns the exit code. This section covers dispatch and `search`.

Take the function `main(argv)`. First, we use interface-based modeling; we know that the function takes in `argv`, thus we model the characteristics of each part of it that the user can vary. To determine important characteristics, we first fixate on the function of the code: the user wants the upgrades that match every filter they gave, and a bad input must produce one clear error line instead of a traceback. We know that the first token decides which handler runs, thus we model which command was given, including no command and an unknown one, and a `load` call that is handed `search` options. Each `search` option has its own validation, so we model `--min-pierce`, `--damage-type`, `--sort` and `--limit` as valid, invalid and absent, since argparse rejects some of them (`SystemExit`) while the query layer rejects others (`ValueError`, exit 2). For the lead and camo flags we model which flags are present, including the contradictory case of naming lead in both `--can-pop` and `--cannot-pop`. For the receiver state, the database file decides whether a query can run at all, so we model whether it is loaded, empty, missing or not a database, and separately whether it holds rows outside the Magic category, which `search` must ignore. How many rows come back is decided by the other characteristics, so it is checked in the oracle rather than modeled.

Fixture: a temporary file `tmp_path / "btd6.db"` (`--db` needs a path, so not `:memory:`), schema from `docs/queries.md`, with these rows (category `Magic`):

| tower | path | projectile_pierce | can_pop_lead | damage_type | can_hit_camo |
|---|---|---|---|---|---|
| Super Monkey | `0-0-0` | 1 | False | Sharp | False |
| Super Monkey | `1-1-0` | 3 | False | Energy | False |
| Super Monkey | `2-0-0` | 2 | True | Plasma | False |
| Super Monkey | `2-1-0` | 3 | True | Plasma | False |

I2 only: add Dart Monkey `0-0-0`, category `Primary`, `projectile_pierce = 3`, `can_pop_lead = False`, `damage_type = Sharp`, `can_hit_camo = False` (inserted by hand).

Base input: `main(["--db", DB, "search", "--cannot-pop", "lead", "--min-pierce", "1"])`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`argv` (subcommand)|A) Which command|A1: `search`|`"search"`|
|||A2: `load` given search options|`"load", "--cannot-pop", "lead", "--min-pierce", "1"`|
|||A3: None|`["--db", DB]`|
|||A4: Unknown|`"fetch"`|
|`--db` (state: file)|B) State before the call|B1: Exists and loaded|the four-row fixture|
|||B2: Exists but empty|schema only, no rows|
|||B3: Missing|`tmp_path / "missing.db"`|
|||B4: Exists but is not a database|a text file containing `hello`|
|`--min-pierce`|C) Value|C1: Valid, at or below stored values|`"1"`|
|||C2: Not a number|`"abc"`|
|||C3: Negative|`"-1"`|
|||C4: Above every stored value|`"4"`|
|`--damage-type`|D) Value|D1: Not given|none|
|||D2: Known name|`"Sharp"`|
|||D3: Unknown name|`"Bogus"`|
|`--sort`|E) Value|E1: Not given|none|
|||E2: Whitelisted column|`"projectile_pierce"`|
|||E3: Not whitelisted|`"bogus"`|
|`--limit`|F) Value|F1: Not given|none|
|||F2: Smallest valid|`"1"`|
|||F3: Below 1|`"0"`|
|`--can-pop` / `--cannot-pop`|G) Lead flags|G1: `--cannot-pop lead`|`"--cannot-pop", "lead"`|
|||G2: `--can-pop lead`|`"--can-pop", "lead"`|
|||G3: Neither|none|
|||G4: Both name lead|`"--can-pop", "lead", "--cannot-pop", "lead"`|
|`--camo` / `--no-camo`|H) Camo flag|H1: Neither|none|
|||H2: `--camo`|`"--camo"`|
|||H3: `--no-camo`|`"--no-camo"`|
|`--db` (state: rows)|I) Non-Magic rows present|I1: None|the four-row fixture|
|||I2: One|fixture plus Dart Monkey `0-0-0`|

Base case: A1, B1, C1, D1, E1, F1, G1, H1, I1

Feasibility notes: A3 and A4 take only `--db`, since search options belong to the `search` subparser, so C through H do not apply to them. B2 to B4 are tested with the base options only.

### Base Choice Coverage

| BCC Test | A | B | C | D | E | F | G | H | I | Oracle | Test Name |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | F1 | G1 | H1 | I1 | returns `0`; stdout is `format_results` of `["0-0-0", "1-1-0"]` | `test_main_search_all_base` |
| T2 | A2 | B1 | C1 | D1 | E1 | F1 | G1 | H1 | I1 | `SystemExit.code == 2`; last stderr line `btd6: error: unrecognized arguments: --cannot-pop lead --min-pierce 1` | `test_main_search_load_given_search_options` |
| T3 | A3 | B1 | — | — | — | — | — | — | I1 | returns `2`; stderr starts with `usage: btd6` | `test_main_search_no_command` |
| T4 | A4 | B1 | — | — | — | — | — | — | I1 | `SystemExit.code == 2`; last stderr line starts with `btd6: error: argument command: invalid choice: 'fetch'` | `test_main_search_unknown_command` |
| T5 | A1 | B2 | C1 | D1 | E1 | F1 | G1 | H1 | I1 | returns `0`; stdout is `No upgrades match these filters.` | `test_main_search_empty_database` |
| T6 | A1 | B3 | C1 | D1 | E1 | F1 | G1 | H1 | I1 | returns `1`; stderr `Database not found at <tmp>/missing.db. Run "python -m btd6 load" first.`; `missing.db` still does not exist afterward | `test_main_search_database_missing` |
| T7 | A1 | B4 | C1 | D1 | E1 | F1 | G1 | H1 | I1 | returns `1`; stderr `Unexpected error: file is not a database`; stderr contains no `Traceback` | `test_main_search_database_not_a_database` |
| T8 | A1 | B1 | C2 | D1 | E1 | F1 | G1 | H1 | I1 | `SystemExit.code == 2`; last stderr line `btd6 search: error: argument --min-pierce: invalid float value: 'abc'` | `test_main_search_min_pierce_not_a_number` |
| T9 | A1 | B1 | C3 | D1 | E1 | F1 | G1 | H1 | I1 | returns `2`; stderr `min_pierce must be 0 or more, got -1.0` | `test_main_search_min_pierce_negative` |
| T10 | A1 | B1 | C4 | D1 | E1 | F1 | G1 | H1 | I1 | returns `0`; stdout is `No upgrades match these filters.` | `test_main_search_min_pierce_above_all` |
| T11 | A1 | B1 | C1 | D2 | E1 | F1 | G1 | H1 | I1 | returns `0`; stdout is `format_results` of `["0-0-0"]` | `test_main_search_damage_type_known` |
| T12 | A1 | B1 | C1 | D3 | E1 | F1 | G1 | H1 | I1 | returns `2`; stderr `Unknown damage type "Bogus". Valid types: Acid, Cold, Energy, Explosion, Fire, Frigid, Glacier, Normal, Plasma, Sharp, Shatter, Unknown` | `test_main_search_damage_type_unknown` |
| T13 | A1 | B1 | C1 | D1 | E2 | F1 | G1 | H1 | I1 | returns `0`; stdout is `format_results` of `["1-1-0", "0-0-0"]` | `test_main_search_sort_whitelisted` |
| T14 | A1 | B1 | C1 | D1 | E3 | F1 | G1 | H1 | I1 | `SystemExit.code == 2`; last stderr line starts with `btd6 search: error: argument --sort: invalid choice: 'bogus'` | `test_main_search_sort_not_whitelisted` |
| T15 | A1 | B1 | C1 | D1 | E1 | F2 | G1 | H1 | I1 | returns `0`; stdout is `format_results` of `["0-0-0"]` | `test_main_search_limit_one` |
| T16 | A1 | B1 | C1 | D1 | E1 | F3 | G1 | H1 | I1 | returns `2`; stderr `limit must be at least 1, got 0` | `test_main_search_limit_zero` |
| T17 | A1 | B1 | C1 | D1 | E1 | F1 | G2 | H1 | I1 | returns `0`; stdout is `format_results` of `["2-0-0", "2-1-0"]` | `test_main_search_can_pop_lead` |
| T18 | A1 | B1 | C1 | D1 | E1 | F1 | G3 | H1 | I1 | returns `0`; stdout is `format_results` of `["0-0-0", "1-1-0", "2-0-0", "2-1-0"]` | `test_main_search_no_lead_flags` |
| T19 | A1 | B1 | C1 | D1 | E1 | F1 | G4 | H1 | I1 | returns `2`; stderr `--can-pop and --cannot-pop both list lead` | `test_main_search_lead_in_both_flags` |
| T20 | A1 | B1 | C1 | D1 | E1 | F1 | G1 | H2 | I1 | returns `0`; stdout is `No upgrades match these filters.` | `test_main_search_camo` |
| T21 | A1 | B1 | C1 | D1 | E1 | F1 | G1 | H3 | I1 | returns `0`; stdout is `format_results` of `["0-0-0", "1-1-0"]` | `test_main_search_no_camo` |
| T22 | A1 | B1 | C1 | D1 | E1 | F1 | G1 | H1 | I2 | with Dart Monkey `0-0-0` inserted, returns `0`; stdout is `format_results` of Super Monkey `["0-0-0", "1-1-0"]`; Dart Monkey is absent | `test_main_search_non_magic_rows_excluded` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T23 | `--help` (#41) | `main(["--help"])` raises `SystemExit` with code `0`; stdout contains `load` and `search` | `test_main_help` |
| T24 | `--debug` (#46) | `main(["--debug", "--db", <B4 file>, "search"])` returns `1`; stderr contains `Traceback` and ends with a line containing `file is not a database` | `test_main_search_debug_traceback` |
| T25 | no filters (#43) | `main(["--db", DB, "search"])` returns `0`; stdout is `format_results` of all four fixture paths | `test_main_search_no_filters` |
| T26 | epic example (#43) | `main(["--db", DB, "search", "--cannot-pop", "lead", "--min-pierce", "3", "--sort", "projectile_pierce", "--limit", "5"])` returns `0`; stdout is `format_results` of `["1-1-0"]` | `test_main_search_epic_example` |

---

## format_results (#44)

```python
def format_results(rows: list[sqlite3.Row]) -> str
```

Renders `search_upgrades` result rows as an aligned text table, or a fixed message when there are none.

Rules:
- Build a `pandas.DataFrame` and render with `to_string(index=False)`, with pandas' row and column display limits turned off (`pd.option_context`).
- Columns, in order, with these headers: `tower` (`tower_name`), `path`, `type` (`damage_type`), `damage` (`projectile_damage`), `pierce` (`projectile_pierce`), `range`, `speed` (`projectile_speed`), `rate` (`attack_rate`), `camo` (`can_hit_camo`), `lead`, `black`, `white`, `purple`, `glass`, `frozen` (the `can_pop_*` flags). Short headers keep the table at 99 characters; the full column names would be 199 and wrap on a 120-column terminal.
- `NULL` prints as `-`. `can_hit_camo` and `can_pop_*` print as `yes` / `no`. A whole number prints without `.0` (`50`, not `50.0`); other numbers print as stored (`0.045`).
- Zero rows return `No upgrades match these filters.`

Fixtures (schema from the migration, built with the helpers in `tests/test_query.py`; rows come from `search_upgrades`):
- Base (T1, T6): the four-row Super Monkey database, filtered with `can_pop_lead=False`, giving `0-0-0`, `1-1-0`.
- T3: all 64 rows of `data.csv`.
- T4, T5: a two-row database with Super Monkey `0-0-0` (changed as in the block's value) and `1-1-0`.

Expected strings have no trailing spaces; lines are joined with `\n`.

Take the function `format_results`. The caller wants a table a player can scan, so we model how many rows are given (none returns a message instead of a table, and more rows than pandas shows by default must not be cut with `...`). Stats can be `NULL`, which must print as `-`, so we model a `NULL` stat. The `Unknown` damage type stores `NULL` `can_pop_*` flags, which must print as `-` rather than `no`, so we model it separately from a `NULL` stat.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`rows`|A) Number of rows|A1: Two|`0-0-0`, `1-1-0`|
|||A2: None|`[]`|
|||A3: More than pandas' default display limit (60)|all 64 rows of `data.csv`|
|`rows` (stat values)|B) `NULL` in a stat column|B1: No `NULL` stat|the base rows|
|||B2: A stat is `NULL`|`0-0-0` with `projectile_pierce = NULL`, plus `1-1-0`|
|`rows` (flag values)|C) `can_pop_*` flags|C1: Flags are set (known damage type)|the base rows|
|||C2: Flags are `NULL` (`Unknown` damage type)|`0-0-0` with `damage_type = Unknown`, plus `1-1-0`|

Base case: A1, B1, C1

Feasibility notes: A2 has no rows, so B and C do not apply to it. B2 uses pierce as its representative: every stat cell goes through the same formatting, so other `NULL` stats are not tested separately.

### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | returns the exact string in block T1 below | `test_format_results_two_rows` |
| T2 | A2 | — | — | returns `No upgrades match these filters.` | `test_format_results_no_rows` |
| T3 | A3 | B1 | C1 | returns 65 lines (header plus 64 rows); no line contains `...` | `test_format_results_no_truncation` |
| T4 | A1 | B2 | C1 | returns the exact string in block T4 below | `test_format_results_null_stat` |
| T5 | A1 | B1 | C2 | returns the exact string in block T5 below | `test_format_results_unknown_damage_type` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T6 | width (#44 acceptance) | for the T1 output, every line is at most 120 characters | `test_format_results_fits_120_columns` |

Expected output T1:

```text
       tower  path   type damage pierce range speed  rate camo lead black white purple glass frozen
Super Monkey 0-0-0  Sharp      1      1    50   200 0.045   no   no   yes   yes    yes   yes     no
Super Monkey 1-1-0 Energy      1      3    60   200 0.045   no   no   yes   yes     no    no    yes
```

Expected output T4:

```text
       tower  path   type damage pierce range speed  rate camo lead black white purple glass frozen
Super Monkey 0-0-0  Sharp      1      -    50   200 0.045   no   no   yes   yes    yes   yes     no
Super Monkey 1-1-0 Energy      1      3    60   200 0.045   no   no   yes   yes     no    no    yes
```

Expected output T5:

```text
       tower  path    type damage pierce range speed  rate camo lead black white purple glass frozen
Super Monkey 0-0-0 Unknown      1      1    50   200 0.045   no    -     -     -      -     -      -
Super Monkey 1-1-0  Energy      1      3    60   200 0.045   no   no   yes   yes     no    no    yes
```

---

## main: `load`

```python
def main(argv: list[str] | None = None) -> int
```

Parses `argv` for the `load` subcommand, fetches each requested Magic tower, writes its upgrades to the database and prints one `<Tower>: <n> upgrades` line per tower.

Take the `load` path of `main(argv)`. First, we use interface-based modeling; we know that `load` takes an optional `--tower`, thus we model which towers were requested: all of them, one valid one, and one that is not a Magic tower, which argparse must reject before any fetch. To determine important characteristics, we first fixate on the function of the code: the user wants every requested tower in the database, and a failure must name what failed. We know that the wiki is the only external dependency, thus we model the fetch outcome: every tower succeeds, one tower returns bad data (the load continues and the exit code is 1), or the wiki is unreachable (every tower fails with the same connection error, and the CLI prints one wiki line). Finally, we model the state of the database file, since loading into a database that already holds the data must not duplicate rows. The `COUNT(*)` and the stdout lines follow from those choices, so they are checked in the oracle.

Fixture: a fake fetch monkeypatched over `btd6.cli.fetch_tower_module` (the CLI passes it to `refresh_database` at call time) that returns the saved Super Monkey module for every tower, so each loads 64 upgrades. Never call the real wiki. Towers load in `MAGIC_TOWERS` order: Super Monkey, Wizard Monkey, Ninja Monkey, Alchemist, Druid. `COUNT(*)` means `SELECT COUNT(*) FROM upgrades` on `NEW_DB` after the call.

Base input: `main(["--db", NEW_DB, "load"])`, with `NEW_DB = tmp_path / "new.db"` not yet created.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`--tower`|A) Towers requested|A1: Not given (all Magic towers)|none|
|||A2: One Magic tower|`"--tower", "Wizard Monkey"`|
|||A3: Not a Magic tower|`"--tower", "Dart Monkey"`|
|fetch|B) Fetch outcome|B1: Every tower succeeds|fake returns the Super Monkey module|
|||B2: One tower has bad data|fake raises `ValueError("no upgrade data")` for `Alchemist`|
|||B3: Wiki unreachable|fake raises `requests.ConnectionError("connection refused")` for every tower|
|`--db` (state: file)|C) State before the call|C1: Missing|`NEW_DB` not created|
|||C2: Already loaded|`NEW_DB` after one successful base `load`|

Base case: A1, B1, C1

Feasibility notes: `refresh_database` tries every tower and reports all failures together, so under B3 every tower fails; the CLI then prints one wiki line instead of one line per tower. The tower list does not change that outcome.

### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | returns `0`; stdout is five lines: `Super Monkey: 64 upgrades`, `Wizard Monkey: 64 upgrades`, `Ninja Monkey: 64 upgrades`, `Alchemist: 64 upgrades`, `Druid: 64 upgrades`; `NEW_DB` exists; `COUNT(*)` is `320` | `test_main_load_all_base` |
| T2 | A2 | B1 | C1 | returns `0`; stdout is `Wizard Monkey: 64 upgrades`; `COUNT(*)` is `64` | `test_main_load_one_tower` |
| T3 | A3 | B1 | C1 | `SystemExit.code == 2`; last stderr line starts with `btd6 load: error: argument --tower: invalid choice: 'Dart Monkey'`; `NEW_DB` is not created | `test_main_load_not_a_magic_tower` |
| T4 | A1 | B2 | C1 | returns `1`; stdout is the four success lines without Alchemist; stderr `Alchemist: failed: no upgrade data`; `COUNT(*)` is `256` | `test_main_load_one_tower_bad_data` |
| T5 | A1 | B3 | C1 | returns `1`; stderr `Could not reach the wiki: connection refused`; stdout is empty | `test_main_load_wiki_unreachable` |
| T6 | A1 | B1 | C2 | returns `0`; stdout is the same five lines as T1; `COUNT(*)` is still `320` | `test_main_load_already_loaded` |

---

## main: `rank` (#99)

```python
def main(argv: list[str] | None = None) -> int
```

Parses `argv` for the `rank` subcommand, builds filters the same way as `search`, calls `rank_upgrades(connection, filters, metric, difficulty, limit)` and prints a pandas table with columns `rank`, `tower`, `path`, `cost`, `DPS`, `damage per dollar` (rank starts at 1, rows in `rank_upgrades` order).

Rules for these tests:
- `rank` accepts every `search` filter option (`--can-pop`, `--cannot-pop`, `--min-*`, `--damage-type`, `--camo`, `--limit`) plus `--metric {dps,dollar,pierce-dollar}` (maps to `dps`, `damage_per_dollar`, `pierce_damage_per_dollar`; default `dollar`) and `--difficulty {easy,medium,hard,impoppable}` (default `medium`). `--sort` is not a `rank` option.
- Tests do not pin number formatting. They parse each data line into rank, tower, path, cost, DPS, damage per dollar and compare against `rank_upgrades` on the same database (numbers with `pytest.approx`).
- Argparse errors check the last stderr line; query-layer errors (`QueryError`) return 2 with one stderr line.

Fixture: the four-path Super Monkey database from `tests/test_ranking.py` (`0-0-0`, `1-0-0`, `3-0-0`, `0-0-4`, all with costs) copied to `tmp_path / "btd6.db"`.

Base input: `main(["--db", DB, "rank"])`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`--metric`|A) Value|A1: Not given (default `dollar`)|none|
|||A2: `dps`|`"dps"`|
|||A3: `pierce-dollar`|`"pierce-dollar"`|
|||A4: Not a choice (`damage_per_dollar` spelling is also invalid)|`"bogus"`|
|`--difficulty`|B) Value|B1: Not given (default `medium`)|none|
|||B2: `easy`|`"easy"`|
|||B3: `impoppable`|`"impoppable"`|
|||B4: Not a choice|`"nightmare"`|
|`--limit`|C) Value|C1: Not given|none|
|||C2: Smallest valid|`"1"`|
|||C3: Below 1|`"0"`|
|||C4: Not an integer|`"abc"`|
|search filters|D) Filter given|D1: None|none|
|||D2: `--can-pop lead`|`"--can-pop", "lead"`|
|||D3: Matches nothing|`"--min-pierce", "99"`|
|||D4: Same property in both pop flags|`"--can-pop", "lead", "--cannot-pop", "lead"`|
|`--db` (state)|E) State before the call|E1: Loaded with costs|the four-row fixture|
|||E2: Missing|`tmp_path / "missing.db"`|

Base case: A1, B1, C1, D1, E1

### Base Choice Coverage

| BCC Test | A | B | C | D | E | Oracle | Test Name |
|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | returns `0`; table equals `rank_upgrades(metric="damage_per_dollar", difficulty="medium")`; header columns in order | `test_main_rank_all_base` |
| T2 | A2 | B1 | C1 | D1 | E1 | table equals `rank_upgrades(metric="dps")` | `test_main_rank_metric_choices` |
| T3 | A3 | B1 | C1 | D1 | E1 | table equals `rank_upgrades(metric="pierce_damage_per_dollar")` | `test_main_rank_metric_choices` |
| T4 | A4 | B1 | C1 | D1 | E1 | `SystemExit.code == 2`; last stderr line starts with `btd6 rank: error: argument --metric: invalid choice: 'bogus'` | `test_main_rank_metric_invalid` |
| T5 | A1 | B2 | C1 | D1 | E1 | table equals `rank_upgrades(difficulty="easy")` | `test_main_rank_difficulty_choices` |
| T6 | A1 | B3 | C1 | D1 | E1 | table equals `rank_upgrades(difficulty="impoppable")` | `test_main_rank_difficulty_choices` |
| T7 | A1 | B4 | C1 | D1 | E1 | `SystemExit.code == 2`; last stderr line starts with `btd6 rank: error: argument --difficulty: invalid choice: 'nightmare'` | `test_main_rank_difficulty_invalid` |
| T8 | A1 | B1 | C2 | D1 | E1 | one data row, equal to the first `rank_upgrades` row | `test_main_rank_limit_one` |
| T9 | A1 | B1 | C3 | D1 | E1 | returns `2`; stderr `limit must be at least 1, got 0`; stdout empty | `test_main_rank_limit_zero` |
| T10 | A1 | B1 | C4 | D1 | E1 | `SystemExit.code == 2`; last stderr line `btd6 rank: error: argument --limit: invalid int value: 'abc'` | `test_main_rank_limit_not_an_integer` |
| T11 | A1 | B1 | C1 | D2 | E1 | table equals `rank_upgrades` with `can_pop_lead=True`, `category="Magic"` | `test_main_rank_can_pop_lead` |
| T12 | A1 | B1 | C1 | D3 | E1 | returns `0`; stdout is `No upgrades match these filters.` | `test_main_rank_no_match` |
| T13 | A1 | B1 | C1 | D4 | E1 | returns `2`; stderr `--can-pop and --cannot-pop both list lead`; stdout empty | `test_main_rank_lead_in_both_flags` |
| T14 | A1 | B1 | C1 | D1 | E2 | returns `1`; stderr `Database not found at <path>. Run "python -m btd6 load" first.`; file not created | `test_main_rank_database_missing` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T15 | defaults (#99) | no options gives the same stdout as `--metric dollar --difficulty medium` | `test_main_rank_defaults_match_explicit` |
| T16 | difficulty changes cost (#99) | cost of `0-0-0` under `hard` is above its cost under `easy` | `test_main_rank_difficulty_changes_cost` |
| T17 | rank column (#99) | ranks printed are `1..n` in order | `test_main_rank_ranks_are_sequential` |
| T18 | `--help` | `main(["--help"])` stdout contains `rank` | `test_main_help_lists_rank` |
| T19 | property | for any metric, difficulty, limit, printed rows equal `rank_upgrades` rows | `test_main_rank_matches_rank_upgrades_property` |

---

## main: `load` with rounds and `--no-rounds` (#86)

```python
def main(argv: list[str] | None = None) -> int
```

`load` also fetches bloons and the default roundset (rounds 1-100) after the towers, writes them with `load_bloons` and `load_rounds`, and prints `Rounds: <r> rounds, <g> groups` after the tower lines. `--no-rounds` skips bloons and rounds entirely: no fetch, no tables written, no `Rounds:` line. A failing rounds step does not hide the tower results (same rule as one failing tower).

Take the `load` path of `main(argv)`. First, we use interface-based modeling; we know that `load` takes an optional `--no-rounds` flag, thus we model whether it was given. The wiki is the only external dependency, thus we model the fetch outcome for the new data: it succeeds, the bloons fetch fails (rounds cannot be linked to bloon ids, so the rounds step is skipped), or the roundset fetch fails. Finally we model the database state, since a second load must leave the counts unchanged. Tower fetching is held at its base (every tower succeeds) and is covered in the section above; row counts and stdout follow from these choices and are checked in the oracle.

Fixture: as in `main: load`, plus fakes over `btd6.cli.fetch_bloons` (returns raw Cargo rows for `Red`, `Blue`, `Moab`) and `btd6.cli.fetch_roundset` (round 1 = `Red` x20; round 2 = `Red` x35; round 3 = `Red` x5, `BlueCamo` x3, `Red` x2). That is 3 rounds and 5 groups. The existing `load` tests (T1-T6 above) install these fakes too, so they never reach the wiki; their stdout then also ends with `Rounds: 3 rounds, 5 groups`. Open decision: the tower tests keep asserting only the five tower lines through `startswith`/line filtering, or each test is updated to the full output.

Base input: `main(["--db", NEW_DB, "load"])`, `NEW_DB` not yet created.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`--no-rounds`|A) Flag|A1: Not given **(Base)**|none|
|||A2: Given|`"--no-rounds"`|
|fetch (new data)|B) Fetch outcome|B1: Bloons and roundset succeed **(Base)**|fakes as above|
|||B2: Bloons fetch fails|`fetch_bloons` raises `ValueError("Wiki cargo query returned no rows")`|
|||B3: Roundset fetch fails|`fetch_roundset` raises `ValueError('Roundset "DefaultRoundSet" not found on the wiki')`|
|`--db` (state: file)|C) State before the call|C1: Missing **(Base)**|`NEW_DB` not created|
|||C2: Already loaded with rounds|`NEW_DB` after one successful base `load`|

Base case: A1, B1, C1

Excluded or reduced combinations: with A2 no rounds fetch happens, so B does not apply; A2 is tested with B1 fakes installed and asserted never called.

### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | returns `0`; the last stdout line is `Rounds: 3 rounds, 5 groups`; `COUNT(*)` of `rounds` is `3`, of `round_groups` is `5`, of `bloons` is `3` | `test_main_load_rounds_base` |
| T2 | A2 | B1 | C1 | returns `0`; stdout has the five tower lines and no `Rounds:` line; `rounds`, `round_groups` and `bloons` are empty; neither fake was called | `test_main_load_no_rounds_flag` |
| T3 | A1 | B2 | C1 | returns `1`; stderr `Bloons: failed: Wiki cargo query returned no rows`; the 320 upgrade rows are still loaded; `rounds` is empty; no `Rounds:` line | `test_main_load_bloons_fetch_fails` |
| T4 | A1 | B3 | C1 | returns `1`; stderr `Rounds: failed: Roundset "DefaultRoundSet" not found on the wiki`; the 320 upgrade rows and the 3 bloons are loaded; `round_groups` is empty | `test_main_load_roundset_fetch_fails` |
| T5 | A1 | B1 | C2 | returns `0`; counts still 3 rounds, 5 groups, 3 bloons and 320 upgrades; the stdout `Rounds:` line is unchanged | `test_main_load_rounds_already_loaded` |

Extra tests, not BCC: `--no-rounds` on a database that already holds rounds leaves them untouched (`test_main_load_no_rounds_keeps_existing_rounds`); `--no-rounds` combined with `--tower Wizard Monkey` loads one tower only and no rounds (`test_main_load_no_rounds_with_tower`); `--tower` given without `--no-rounds` still loads rounds, since rounds do not depend on the tower list.

---

## main: `rounds` threats (#118)

With `--round N` (one round), `rounds` prints a blank line and then the `round_threats` summary after the table: `Threats (round N)`, `total RBE`, `unknown groups`, one `<property>: <share>%` line per property, `camo`, `regrow`, `moab` (shares with one decimal) and `mean layers` (two decimals). A `--from/--to` range prints no summary. Tests: `test_main_rounds_single_round_prints_threats` (round 27, Lead x6: lead 100.0%), `test_main_rounds_moab_round_threats` (round 40: moab 86.0%) and `test_main_rounds_range_has_no_threats`. Characteristic: A) selection kind (A1 `--round` **(Base)**, A2 `--from/--to`); BCC: T1 (A1) prints the summary, T2 (A2) does not.

## main: `rounds` (#87)

The `rounds` subcommand (`--round N`, `--from A --to B`) has its ISP and BCC tables, with the fixture and the 10 base-choice tests, in `tests/isp-tables/round_queries.md` (section `main: rounds`), next to the `get_round` tables it prints from. Its dispatch counts as a new command in the A block of `main: dispatch and search`: `rounds` is a valid command, and `btd6 --help` lists `load, search, rank, serve, rounds`.

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T1 | help text | `btd6 --help` stdout names `rounds` among the commands | `test_main_help_lists_rounds_command` |

---

## main: `income` (#93)

```python
def main(argv: list[str] | None = None) -> int
def income_summary(income: RoundIncome, round_number: int) -> str   # btd6/formatting.py
```

`income --round N` prints `income_summary(round_income(connection, N), N)`. `income --up-to N` prints a pandas table (`to_string(index=False)`, display limits off) with one row per round 1..N and columns `round`, `pop cash`, `end bonus`, `total`, `running total` (`running total` is `cumulative_income` up to that round). Table cells are plain numbers with no `$` and no thousands separators, whole numbers without `.0`, otherwise rounded to 1 decimal (`1220.2`). Exactly one of `--round` / `--up-to` is required (argparse mutually exclusive group, `required=True`). Spec: `docs/income.md`.

Errors: `validate_round` `ValueError` (round out of range) returns 2 with the message `Round <n> is not loaded; loaded rounds are 1-<last>`; `NoRoundDataError` returns 1 with `No round data loaded. Run "python -m btd6 load" first.` (same as `rounds`); a `ValueError` for missing income data (no thresholds or settings) returns 1 with one stderr line that mentions income and ends `Run "python -m btd6 load" first.` The source must tell these apart (e.g. the CLI checks for income tables before computing).

### income_summary format

`Round <n>: $<pop cash> pop cash + $<end bonus> end bonus = $<total>`. Each amount is rounded to 1 decimal, grouped with commas, and a trailing `.0` is dropped: `$20`, `$1,220.2`, `$2,663`, `$0.3` (float noise such as `0.30000000000000004` is rounded away).

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`argv` (selection)|A) Which selector|A1: `--round` only **(Base)**|`"--round", "1"`|
|||A2: `--up-to` only|`"--up-to", "5"`|
|||A3: Neither|none|
|||A4: Both|`"--round", "1", "--up-to", "5"`|
|`--round` / `--up-to` (value)|B) Round value|B1: In range **(Base)**|`1`|
|||B2: Last loaded round|`100`|
|||B3: Zero|`0`|
|||B4: Above last loaded|`101`|
|||B5: Negative (`--round` only)|`-1`|
|||B6: Not an integer|`"abc"`|
|`--db` (state)|C) State before the call|C1: Rounds 1-100 and income loaded **(Base)**|`income_db` fixture saved to a file|
|||C2: Missing|`tmp_path / "missing.db"`|
|||C3: Schema only, no rounds|migrations applied, no rows|
|||C4: Rounds but no income thresholds|`build_connection(5, with_income=False)`|
|||C5: Rounds 1-5 only|`build_connection(5)`|

Base case: A1, B1, C1

### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | returns `0`; stdout is `Round 1: $20 pop cash + $101 end bonus = $121`; stderr empty | `test_main_income_round_one` |
| T2 | A2 | B1 | C1 | returns `0`; header `round, pop cash, end bonus, total, running total`; one row `1 20 101 121 121` | `test_main_income_up_to_one` |
| T3 | A3 | B1 | C1 | `SystemExit.code == 2`; last stderr line `btd6 income: error: one of the arguments --round --up-to is required` | `test_main_income_argparse_errors` |
| T4 | A4 | B1 | C1 | `SystemExit.code == 2`; last stderr line `btd6 income: error: argument --up-to: not allowed with argument --round` | `test_main_income_argparse_errors` |
| T5 | A1 | B2 | C1 | returns `0`; stdout `Round 100: $1,334.6 pop cash + $200 end bonus = $1,534.6` | `test_main_income_round_prints_income_summary` |
| T6 | A1 | B3 | C1 | returns `2`; stderr `Round 0 is not loaded; loaded rounds are 1-100`; stdout empty | `test_main_income_out_of_range` |
| T7 | A1 | B4 | C1 | returns `2`; stderr `Round 101 is not loaded; loaded rounds are 1-100` | `test_main_income_out_of_range` |
| T8 | A1 | B5 | C1 | returns `2`; stderr `Round -1 is not loaded; loaded rounds are 1-100` | `test_main_income_out_of_range` |
| T9 | A1 | B6 | C1 | `SystemExit.code == 2`; last stderr line `btd6 income: error: argument --round: invalid int value: 'abc'` | `test_main_income_argparse_errors` |
| T10 | A1 | B1 | C2 | returns `1`; stderr `Database not found at <path>. Run "python -m btd6 load" first.`; file not created | `test_main_income_database_missing` |
| T11 | A1 | B1 | C3 | returns `1`; stderr `No round data loaded. Run "python -m btd6 load" first.`; stdout empty | `test_main_income_no_round_data` |
| T12 | A1 | B1 | C4 | returns `1`; one stderr line mentioning income and `Run "python -m btd6 load" first.`; stdout empty | `test_main_income_no_income_data` |
| T13 | A2 | B4 | C1 | returns `2`; stderr `Round 101 is not loaded; loaded rounds are 1-100` | `test_main_income_out_of_range` |
| T14 | A2 | B3 | C1 | returns `2`; stderr `Round 0 is not loaded; loaded rounds are 1-100` | `test_main_income_out_of_range` |
| T15 | A2 | B2 | C1 | returns `0`; 100 data rows; last running total `178994.4` | `test_main_income_up_to_last_round` |
| T16 | A2 | B6 | C1 | `SystemExit.code == 2`; last stderr line `btd6 income: error: argument --up-to: invalid int value: 'x'` | `test_main_income_argparse_errors` |
| T17 | A2 | B1 | C5 | `--up-to 6` returns `2`; stderr `Round 6 is not loaded; loaded rounds are 1-5` | `test_main_income_short_database_bounds` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T18 | worked examples | `--up-to 5` rows `1 20 101 121 121` ... `5 59 105 164 735` | `test_main_income_up_to_five` |
| T19 | epic example | `--up-to 40` has 40 rows, last `40 381 140 521 16856` | `test_main_income_up_to_forty` |
| T20 | fractional cells | `--up-to 80` last row starts `80 1220.2 180 1400.2` | `test_main_income_up_to_fractional_cells` |
| T21 | `--round 80` | `Round 80: $1,220.2 pop cash + $180 end bonus = $1,400.2` | `test_main_income_round_fractional` |
| T22 | table agrees with summary | `--up-to 63` last row `63 2663 163 2826`; `--round 63` shows `$2,663 pop cash` and `$2,826` | `test_main_income_up_to_row_agrees_with_round` |
| T23 | property | for any `up_to` in 1..100: rows are rounds `1..up_to`, last running total equals `cumulative_income`, running totals never decrease, `total = pop cash + end bonus` | `test_main_income_up_to_matches_income_functions` |
| T24 | `--round` equals `income_summary` | for rounds 40, 63, 80, 100 stdout is `income_summary(round_income(...), n)` plus newline | `test_main_income_round_prints_income_summary` |
| T25 | help | `income --help` lists `--round`, `--up-to`; `btd6 --help` lists `income` | `test_main_income_help_lists_options`, `test_main_help_lists_income_command` |

### income_summary (`tests/test_formatting_income.py`)

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`income.pop_cash`|A) Shape|A1: Whole **(Base)**|`381.0`|
|||A2: One decimal|`1220.2`|
|||A3: Zero|`0.0`|
|||A4: Float noise|`0.1 + 0.2`|
|||A5: Integer type|`20`|
|`income` (size)|B) Thousands|B1: Below 1,000 **(Base)**|`381.0`|
|||B2: Exactly 1,000|`1000.0`|
|||B3: Above 1,000|`2663.0`, `1334.6`|

Base case: A1, B1. Cases: `test_income_summary` (parametrized, 9 rows listed in the file) and `test_income_summary_properties` (hypothesis: prefix `Round <n>: $`, one line, no `.0` suffix, total round-trips within 0.05).

---

## main: `recommend` (#123)

```python
def main(argv: list[str] | None = None) -> int
```

`recommend --round N --money X [--difficulty D] [--limit N]` calls `recommend(connection, N, X, difficulty, limit)` (`docs/recommend.md`) and prints a pandas table (`to_string(index=False)`, display limits off) with columns `rank`, `tower`, `path`, `cost`, `score`, `reasons` (rank starts at 1; `reasons` joined with `", "`; a NULL score prints `-`). An empty result prints `No affordable upgrade can handle this round.`

Rules for these tests:
- `--round` and `--money` are required `int` options; `--difficulty` uses the `rank` choices (default `medium`); `--limit` is an `int`.
- Tests parse each data line into rank, tower, path, cost, score and compare against `recommend` on the same database. Number formatting is not pinned: compare the score with `pytest.approx(abs=1e-4)`.
- `QueryError` returns 2 with its message on one stderr line; `NoRoundDataError` returns 1 with `No round data loaded. Run "python -m btd6 load" first.`

Fixture: the recommender fixture (`tests/recommend_fixture.py`: four Super Monkey upgrades with costs, rounds 1-101) saved to `tmp_path / "btd6.db"`.

Base input: `main(["--db", DB, "recommend", "--round", "63", "--money", "100000"])`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`--round`|A) Value|A1: Loaded round|`"63"`|
|||A2: Not loaded|`"150"`|
|||A3: Missing|none|
|||A4: Not an integer|`"abc"`|
|`--money`|B) Value|B1: Above every cost|`"100000"`|
|||B2: Below the cheapest|`"100"`|
|||B3: Negative|`"-1"`|
|||B4: Missing|none|
|`--difficulty`|C) Value|C1: Not given|none|
|||C2: `hard`|`"hard"`|
|||C3: Not a choice|`"nightmare"`|
|`--limit`|D) Value|D1: Not given|none|
|||D2: One|`"1"`|
|||D3: Zero|`"0"`|
|`--db` (state)|E) State before the call|E1: Loaded|recommender fixture|
|||E2: Missing|`tmp_path / "missing.db"`|
|||E3: No rounds loaded|fixture with `rounds`/`round_groups` emptied|

Base case: A1, B1, C1, D1, E1

### Base Choice Coverage

| BCC Test | A | B | C | D | E | Oracle | Test Name |
|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | returns `0`; rows `3-0-0` then `0-0-4`; `3-0-0` reasons `affordable, pops_lead, high_pierce`; header `rank tower path cost score reasons` | `test_main_recommend_all_base` |
| T2 | A2 | B1 | C1 | D1 | E1 | returns `2`; stderr `Round 150 is not loaded; loaded rounds are 1-101` | `test_main_recommend_round_not_loaded` |
| T3 | A3 | B1 | C1 | D1 | E1 | `SystemExit.code == 2`; last stderr line mentions `--round` | `test_main_recommend_round_missing` |
| T4 | A4 | B1 | C1 | D1 | E1 | `SystemExit.code == 2`; last stderr line `btd6 recommend: error: argument --round: invalid int value: 'abc'` | `test_main_recommend_round_not_integer` |
| T5 | A1 | B2 | C1 | D1 | E1 | returns `0`; stdout `No affordable upgrade can handle this round.` | `test_main_recommend_nothing_affordable` |
| T6 | A1 | B3 | C1 | D1 | E1 | returns `2`; stderr `money must be 0 or more, got -1` | `test_main_recommend_negative_money` |
| T7 | A1 | B4 | C1 | D1 | E1 | `SystemExit.code == 2`; last stderr line mentions `--money` | `test_main_recommend_money_missing` |
| T8 | A1 | B1 | C2 | D1 | E1 | `3-0-0` cost printed is `recommend(..., "hard")` cost (`29160`) | `test_main_recommend_hard` |
| T9 | A1 | B1 | C3 | D1 | E1 | `SystemExit.code == 2`; last stderr line starts `btd6 recommend: error: argument --difficulty: invalid choice: 'nightmare'` | `test_main_recommend_difficulty_invalid` |
| T10 | A1 | B1 | C1 | D2 | E1 | one data row, `3-0-0` | `test_main_recommend_limit_one` |
| T11 | A1 | B1 | C1 | D3 | E1 | returns `2`; stderr `limit must be at least 1, got 0` | `test_main_recommend_limit_zero` |
| T12 | A1 | B1 | C1 | D1 | E2 | returns `1`; stderr `Database not found at <path>. Run "python -m btd6 load" first.` | `test_main_recommend_database_missing` |
| T13 | A1 | B1 | C1 | D1 | E3 | returns `1`; stderr `No round data loaded. Run "python -m btd6 load" first.` | `test_main_recommend_no_round_data` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T14 | help | `btd6 --help` stdout names `recommend` | `test_main_help_lists_recommend` |
| T15 | MOAB round | round 40: first row `0-0-0`, every reasons cell ends in `high_single_target` | `test_main_recommend_moab_round` |

## `start` (one-command launcher)

`python -m btd6 start [--host H] [--port P] [--refresh] [--no-browser] [--game]` builds the database when it is missing (or with `--refresh`), optionally launches BTD6 through Steam, opens the browser once the server accepts connections, then serves.

### ISP

| Input | Characteristic | Block | Value |
|---|---|---|---|
| `--db` (state) | A) State before the call | A1: Exists | empty file |
| | | A2: Missing, load succeeds | `tmp_path / "new.db"`, offline fetch |
| | | A3: Missing, wiki unreachable | `tmp_path / "new.db"`, fetch raises `ConnectionError` |
| | | A4: Exists, `--refresh` | empty file plus `--refresh` |
| `--no-browser` | B) Given | B1: No | none |
| | | B2: Yes | `--no-browser` |
| `--game` | C) Given | C1: No | none |
| | | C2: Yes | `--game` |
| `--host`/`--port` | D) Address | D1: Defaults | none |
| | | D2: All interfaces, custom port | `--host 0.0.0.0 --port 9100` |

Base case: A1, B1, C1, D1

### Base Choice Coverage

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | returns `0`; no load; browser scheduled for `http://127.0.0.1:8000`; uvicorn on `127.0.0.1:8000`; no game launch | `test_start_all_base` |
| T2 | A2 | B1 | C1 | D1 | returns `0`; stdout has `Building the database` and the load lines; upgrades loaded; uvicorn runs | `test_start_builds_missing_database` |
| T3 | A3 | B1 | C1 | D1 | returns `1`; database file removed; uvicorn and browser not called | `test_start_load_failure_removes_new_database` |
| T4 | A4 | B1 | C1 | D1 | returns `0`; load runs on the existing file | `test_start_refresh_reloads` |
| T5 | A1 | B2 | C1 | D1 | browser not scheduled; uvicorn runs | `test_start_no_browser` |
| T6 | A1 | B1 | C2 | D1 | `open_uri` called once with `steam://rungameid/960090` | `test_start_launches_game` |
| T7 | A1 | B1 | C1 | D2 | uvicorn on `0.0.0.0:9100`; browser URL `http://127.0.0.1:9100` | `test_start_custom_address` |

| T7a | A1 | B1 | C1 | D1 | key file E: absent | template written at `cli.KEY_FILE_PATH` before uvicorn runs; stdout has `Created gemini_api_key.txt: paste a free Gemini API key there to use the agent.` | `test_start_creates_key_file_template`, `test_start_creates_key_file_before_serving` |
| T7b | A1 | B1 | C1 | D1 | key file E: exists | file content unchanged; no `Created` line | `test_start_keeps_existing_key_file` |

### Launcher helpers (`btd6/launcher.py`)

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T8 | `browser_url` | `0.0.0.0`/`::`/empty map to `127.0.0.1`; other hosts kept | `test_browser_url` |
| T9 | `open_uri` per platform | `win32` -> `os.startfile`; `darwin` -> `open`; `linux` -> `xdg-open` | `test_open_uri_uses_platform_opener` |
| T10 | `wait_for_port` open | listening socket -> `True` | `test_wait_for_port_open` |
| T11 | `wait_for_port` closed | nothing listening, short timeout -> `False` | `test_wait_for_port_times_out` |
| T12 | `open_browser_when_ready` | thread opens the URL once the port listens; nothing opened when it never does | `test_open_browser_when_ready_*` |

### Restarting: `replace_running_advisor` and `run_start` (`docs/web.md`, Restarting)

```python
def replace_running_advisor(host: str, port: int) -> str | None
```
Returns `None` when the port is free or the old advisor was stopped; otherwise an error message that `run_start` prints to stderr before returning `1`.

#### ISP

| Input | Characteristic | Block | Value |
|---|---|---|---|
| `port_in_use(host, port)` | A) Port state | A1: Free | `False` |
| | | A2: In use | `True` |
| `running_advisor_pid` | B) Health reply | B1: Advisor | `4321` |
| | | B2: No advisor | `None` |
| `wait_for_port_free` | C) Port after SIGTERM | C1: Freed within `STOP_TIMEOUT_SECONDS` | `True` |
| | | C2: Still held | `False` |

Base case: A2, B1, C1 (C is only reachable with B1; B and C are not varied when A1.)

#### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A2 | B1 | C1 | returns `None`; `stop_process(4321)`; waits with `STOP_TIMEOUT_SECONDS`; prints `Stopping the advisor that is already running (pid 4321)...` | `test_replace_running_advisor_stops_old_advisor` |
| T2 | A1 | B1 | C1 | returns `None`; nothing stopped, no output | `test_replace_running_advisor_port_free` |
| T3 | A2 | B2 | C1 | returns `Port 9100 is already in use. ...use --port N.`; nothing stopped | `test_replace_running_advisor_port_held_by_other_program` |
| T4 | A2 | B1 | C2 | returns `Could not stop the advisor on port 8000 (pid 4321). Close its window and run the start script again.` | `test_replace_running_advisor_will_not_stop` |

Extra `run_start` tests (not BCC):

| Test | Oracle | Test Name |
|---|---|---|
| Called with the address | `replace_running_advisor("0.0.0.0", 9100)` | `test_start_checks_the_address_first` |
| Error message | returns `1`; message on stderr; no db built, no game, no uvicorn, no browser | `test_start_port_error_prints_and_exits` |
| Order | replace runs before `build_database` | `test_start_replaces_before_building_database` |

#### `running_advisor_pid(host, port) -> int | None`

`GET http://<host>:<port>/api/health` with a 2 s timeout (wildcard hosts map to `127.0.0.1`).

| Input | Characteristic | Block | Value |
|---|---|---|---|
| response | D) Reply | D1: Valid | `{"app": "btd6", "pid": 4321}` |
| | | D2: Request fails | `ConnectionError`, `Timeout` |
| | | D3: Not JSON | `.json()` raises `ValueError` |
| | | D4: Other app | `{"app": "other", "pid": 4321}` |
| | | D5: `pid` not int | `"4321"`, missing; JSON list or null body |

Base case: D1. Oracles: D1 `4321`; D2 to D5 `None`. Tests: `test_running_advisor_pid_valid_reply`, `test_running_advisor_pid_not_an_advisor` (parametrized), plus wildcard mapping and the 2 s timeout.

#### `stop_process(pid)`, `port_in_use`, `wait_for_port_free`

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T5 | other pid | `os.kill(pid, SIGTERM)` once | `test_stop_process_sends_sigterm` |
| T6 | own pid | `os.kill` not called | `test_stop_process_ignores_own_pid` |
| T7 | `ProcessLookupError` | swallowed, returns `None` | `test_stop_process_already_exited_counts_as_stopped` |
| T8 | `port_in_use` listening / free / wildcard | `True` / `False` / `True` | `test_port_in_use_*` |
| T9 | `wait_for_port_free` free / held / released midway | `True` / `False` after the timeout / `True` | `test_wait_for_port_free_*` |
| T10 | constant | `STOP_TIMEOUT_SECONDS == 10` | `test_stop_timeout_is_ten_seconds` |

### `recommend --one-per-tower` and `--live` owned towers

`recommend` gains `--one-per-tower` (flag, passed as `one_per_tower`) and an `upgrade from` column after `path` (blank for new purchases). With `--live`, the known towers of the game state are passed as `owned`, and a line `Owned: <name> <path>, ...` (or `Owned: none`) is printed under the `Live game:` line. Tests: `tests/test_cli_recommend.py`, `tests/test_cli_live.py`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`--one-per-tower`|K) Flag|K1: Not given|none|
|||K2: Given|`--one-per-tower`|
|`--live` state towers|L) Owned towers|L1: Not live|no `--live`|
|||L2: Live, one known tower the database lacks|`Super Monkey 2-0-0`|
|||L3: Live, one tower that creates upgrades|`Super Monkey 0-0-0`|
|||L4: Live, several towers|`Ninja Monkey 0-0-0`, `Dart Monkey 2-0-0`|
|||L5: Live, none|`[]`|

Base case: K1, L1

### Base Choice Coverage

| BCC Test | K | L | Oracle | Test Name |
|---|---|---|---|---|
| T1 | K1 | L1 | header `rank tower path upgrade from cost score leaks at reasons`; `upgrade from` blank; no `Owned:` line | `test_main_recommend_all_base`, `test_main_recommend_upgrade_from_column_is_blank_for_purchases`, `test_main_recommend_not_live_prints_no_owned_line` |
| T2 | K2 | L1 | one data row equal to `recommend(..., one_per_tower=True)`; also with `--limit 3` | `test_main_recommend_one_per_tower`, `test_main_recommend_one_per_tower_with_limit` |
| T3 | K1 | L2 | line `Owned: Super Monkey 2-0-0`, table equal to the non-live table (entry ignored) | `test_main_recommend_live_all_base`, `test_main_recommend_live_hard` |
| T4 | K1 | L3 | `Owned: Super Monkey 0-0-0`; table has upgrade rows (`upgrades_owned`, price 24500) | `test_main_recommend_live_passes_owned_towers` |
| T5 | K1 | L4 | `Owned: Ninja Monkey 0-0-0, Dart Monkey 2-0-0` | `test_main_recommend_live_lists_every_owned_tower` |
| T6 | K1 | L5 | `Owned: none`, table equal to non-live | `test_main_recommend_live_no_towers` |
| T7 | K2 | L3 | one data row | `test_main_recommend_live_one_per_tower` |

`--help` for `recommend` lists `--one-per-tower` (`test_main_recommend_help_lists_one_per_tower`). A live tower with `known` false is not passed or printed (assumed, untested).
