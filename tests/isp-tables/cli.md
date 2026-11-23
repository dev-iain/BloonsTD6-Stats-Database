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

## main: `gui` (#77)

```python
def main(argv: list[str] | None = None) -> int
```

Parses `argv` for the `gui` subcommand (alias `ui`) and returns `btd6.ui.app.main(args.db)`. `btd6.ui.app.main` is monkeypatched with a spy in every test, so no window opens.

Take the `gui` path of `main(argv)`. The user wants the same window from either spelling and the same `--db` handling as `search`, so we model which spelling was used, whether `--db` was given, and whether the subcommand received options it does not accept.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`argv` (subcommand)|A) Spelling|A1: `gui`|`"gui"`|
|||A2: `ui` alias|`"ui"`|
|`--db`|B) Database path|B1: Given before the subcommand|`"--db", DB`|
|||B2: Not given|none|
|`argv` (extra options)|C) Options after `gui`|C1: None|none|
|||C2: Search option|`"--min-pierce", "1"`|

Base case: A1, B1, C1

### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | spy called once with `DB`; returns the spy's value (`7`) | `test_main_gui_dispatches_to_app_main` |
| T2 | A2 | B1 | C1 | spy called once with `DB`; returns `7` | `test_main_gui_ui_alias` |
| T3 | A1 | B2 | C1 | spy called once with `str(PROJECT_ROOT / "btd6.db")` | `test_main_gui_default_database` |
| T4 | A1 | B1 | C2 | `SystemExit.code == 2`; last stderr line `btd6: error: unrecognized arguments: --min-pierce 1`; spy not called | `test_main_gui_rejects_search_options` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T5 | help | `build_parser().format_help()` lists `gui` | `test_build_parser_lists_gui` |
| T6 | spy raises | `app.main` raising `RuntimeError("boom")` gives return `1` and stderr `Unexpected error: boom` | `test_main_gui_unexpected_error` |

---

## build_window, main, import safety (#77)

```python
def build_window(db_path: str) -> tk.Tk       # btd6/ui/app.py
def main(db_path: str) -> int                  # btd6/ui/app.py
```

`build_window` returns a root holding a `ttk.Notebook` with tabs Search, Rounds, Rankings; Rounds and Rankings each show a "Coming soon" label. `main` builds the window, runs `mainloop`, returns `0`, and closes the SQLite connection (opened through `btd6.ui.app.connect`) when the window closes. Window tests skip on `tk.TclError`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|window|A) Tab|A1: Search|index 0|
|||A2: Rounds|index 1|
|||A3: Rankings|index 2|
|window|B) Window lifecycle|B1: Built, not closed|after `build_window`|
|||B2: Closed through the window manager|`WM_DELETE_WINDOW` invoked during `mainloop`|

Base case: A1, B1

### Base Choice Coverage

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | notebook has exactly 3 tabs, texts `["Search", "Rounds", "Rankings"]` | `test_build_window_tab_titles` |
| T2 | A2 | B1 | tab 1 contains a label with text `Coming soon` | `test_build_window_rounds_placeholder` |
| T3 | A3 | B1 | tab 2 contains a label with text `Coming soon` | `test_build_window_rankings_placeholder` |
| T4 | A1 | B2 | `main` returns `0`; the spy connection's `close` was called once | `test_main_closes_connection_on_window_close` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T5 | no display needed | `btd6.ui.app` has callable `build_window` and `main` | `test_app_exposes_build_window_and_main` |
| T6 | import safety | in a subprocess with `tkinter.Tk` replaced by a function that raises, `import btd6.ui` and `import btd6.ui.app` succeed | `test_import_btd6_ui_creates_no_window` |
| T7 | import safety | `import btd6.ui` alone leaves `tkinter` out of `sys.modules` | `test_import_btd6_ui_does_not_import_tkinter` |
