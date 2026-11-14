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
| unknown damage type (query layer `ValueError`) | 2 | `Unknown damage type "Bogus". Valid types: Acid, Cold, Energy, Explosion, Fire, Frigid, Glacier, Normal, Plasma, Shatter, Sharp, Unknown` |
| limit below 1 (query layer `ValueError`) | 2 | `limit must be at least 1, got 0` |
| same property in `--can-pop` and `--cannot-pop` | 2 | `--can-pop and --cannot-pop both list lead` |
| wiki unreachable during `load` | 1 | `Could not reach the wiki: <reason>` |
| one tower fails during `load` | 1 | `<Tower>: failed: <reason>` |
| any other exception | 1 | `Unexpected error: <message>` |

---

## Table 1: dispatch and `search`

Fixture: a temporary file `tmp_path / "btd6.db"` (`--db` needs a path, so not `:memory:`), schema from `docs/queries.md`, with these rows (category `Magic`):

| tower | path | projectile_pierce | can_pop_lead | damage_type | can_hit_camo |
|---|---|---|---|---|---|
| Super Monkey | `0-0-0` | 1 | False | Sharp | False |
| Super Monkey | `1-1-0` | 3 | False | Energy | False |
| Super Monkey | `2-0-0` | 2 | True | Plasma | False |
| Super Monkey | `2-1-0` | 3 | True | Plasma | False |

J2 only: add Dart Monkey `0-0-0`, category `Primary`, `projectile_pierce = 3`, `can_pop_lead = False`, `damage_type = Sharp`, `can_hit_camo = False` (inserted by hand).

Base input: `main(["--db", DB, "search", "--cannot-pop", "lead", "--min-pierce", "1"])`.

### ISP

| Variable | Characteristic | Partition/Block | Representative Value |
|---|---|---|---|
| V1: subcommand | A: Which command | A1 (Base): `search` | `"search"` |
| V1: subcommand | A: Which command | A2: `load` given search options | `"load", "--cannot-pop", "lead", "--min-pierce", "1"` |
| V1: subcommand | A: Which command | A3: none | `["--db", DB]` |
| V1: subcommand | A: Which command | A4: unknown | `"fetch"` |
| V2: database file | B: State before the call | B1 (Base): exists and loaded | the four-row fixture |
| V2: database file | B: State before the call | B2: exists but empty | schema only, no rows |
| V2: database file | B: State before the call | B3: missing | `tmp_path / "missing.db"` |
| V2: database file | B: State before the call | B4: exists but is not a database | a text file containing `hello` |
| V3: `--min-pierce` | C: Value | C1 (Base): valid, at or below stored values | `"1"` |
| V3: `--min-pierce` | C: Value | C2: not a number | `"abc"` |
| V3: `--min-pierce` | C: Value | C3: negative | `"-1"` |
| V3: `--min-pierce` | C: Value | C4: above every stored value | `"4"` |
| V4: `--damage-type` | D: Value | D1 (Base): not given | — |
| V4: `--damage-type` | D: Value | D2: known name | `"Sharp"` |
| V4: `--damage-type` | D: Value | D3: unknown name | `"Bogus"` |
| V5: `--sort` | E: Value | E1 (Base): not given | — |
| V5: `--sort` | E: Value | E2: whitelisted column | `"projectile_pierce"` |
| V5: `--sort` | E: Value | E3: not whitelisted | `"bogus"` |
| V6: `--limit` | F: Value | F1 (Base): not given | — |
| V6: `--limit` | F: Value | F2: smallest valid | `"1"` |
| V6: `--limit` | F: Value | F3: below 1 | `"0"` |
| V7: `--can-pop` / `--cannot-pop` | H: Lead flags | H1 (Base): `--cannot-pop lead` | `"--cannot-pop", "lead"` |
| V7: `--can-pop` / `--cannot-pop` | H: Lead flags | H2: `--can-pop lead` | `"--can-pop", "lead"` |
| V7: `--can-pop` / `--cannot-pop` | H: Lead flags | H3: neither | — |
| V7: `--can-pop` / `--cannot-pop` | H: Lead flags | H4: both name lead | `"--can-pop", "lead", "--cannot-pop", "lead"` |
| V8: `--camo` / `--no-camo` | I: Camo flag | I1 (Base): neither | — |
| V8: `--camo` / `--no-camo` | I: Camo flag | I2: `--camo` | `"--camo"` |
| V8: `--camo` / `--no-camo` | I: Camo flag | I3: `--no-camo` | `"--no-camo"` |
| V2: database file | J: Non-magic rows present | J1 (Base): none | the four-row fixture |
| V2: database file | J: Non-magic rows present | J2: one | fixture plus Dart Monkey `0-0-0` |
| output | G: Number of result rows | G1 (Base): many | base input -> 2 rows |
| output | G: Number of result rows | G2: one | `--damage-type Sharp` -> 1 row |
| output | G: Number of result rows | G3: zero | `--min-pierce 4` -> no rows |

A3 and A4 take only `--db`, since search options belong to the `search` subparser.

### Base Choice Coverage

G is excluded from BCC: the row count is decided by the other characteristics (G2 in BCC-11 and BCC-15, G3 in BCC-5, BCC-10 and BCC-20).

| Case ID | A | B | C | D | E | F | H | I | J | Changed characteristic | Expected result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BCC-1 | A1 | B1 | C1 | D1 | E1 | F1 | H1 | I1 | J1 | None — All Base | returns `0`; stdout is `format_results` of `["0-0-0", "1-1-0"]` |
| BCC-2 | A2 | B1 | C1 | D1 | E1 | F1 | H1 | I1 | J1 | A | `SystemExit.code == 2`; last stderr line `btd6: error: unrecognized arguments: --cannot-pop lead --min-pierce 1` |
| BCC-3 | A3 | B1 | — | — | — | — | — | — | J1 | A | returns `2`; stderr starts with `usage: btd6` |
| BCC-4 | A4 | B1 | — | — | — | — | — | — | J1 | A | `SystemExit.code == 2`; last stderr line starts with `btd6: error: argument command: invalid choice: 'fetch'` |
| BCC-5 | A1 | B2 | C1 | D1 | E1 | F1 | H1 | I1 | J1 | B | returns `0`; stdout is `No upgrades match these filters.` |
| BCC-6 | A1 | B3 | C1 | D1 | E1 | F1 | H1 | I1 | J1 | B | returns `1`; stderr `Database not found at <tmp>/missing.db. Run "python -m btd6 load" first.`; `missing.db` still does not exist afterward |
| BCC-7 | A1 | B4 | C1 | D1 | E1 | F1 | H1 | I1 | J1 | B | returns `1`; stderr `Unexpected error: file is not a database`; stderr contains no `Traceback` |
| BCC-8 | A1 | B1 | C2 | D1 | E1 | F1 | H1 | I1 | J1 | C | `SystemExit.code == 2`; last stderr line `btd6 search: error: argument --min-pierce: invalid float value: 'abc'` |
| BCC-9 | A1 | B1 | C3 | D1 | E1 | F1 | H1 | I1 | J1 | C | returns `2`; stderr `min_pierce must be 0 or more, got -1.0` |
| BCC-10 | A1 | B1 | C4 | D1 | E1 | F1 | H1 | I1 | J1 | C | returns `0`; stdout is `No upgrades match these filters.` |
| BCC-11 | A1 | B1 | C1 | D2 | E1 | F1 | H1 | I1 | J1 | D | returns `0`; stdout is `format_results` of `["0-0-0"]` |
| BCC-12 | A1 | B1 | C1 | D3 | E1 | F1 | H1 | I1 | J1 | D | returns `2`; stderr `Unknown damage type "Bogus". Valid types: Acid, Cold, Energy, Explosion, Fire, Frigid, Glacier, Normal, Plasma, Shatter, Sharp, Unknown` |
| BCC-13 | A1 | B1 | C1 | D1 | E2 | F1 | H1 | I1 | J1 | E | returns `0`; stdout is `format_results` of `["1-1-0", "0-0-0"]` |
| BCC-14 | A1 | B1 | C1 | D1 | E3 | F1 | H1 | I1 | J1 | E | `SystemExit.code == 2`; last stderr line starts with `btd6 search: error: argument --sort: invalid choice: 'bogus'` |
| BCC-15 | A1 | B1 | C1 | D1 | E1 | F2 | H1 | I1 | J1 | F | returns `0`; stdout is `format_results` of `["0-0-0"]` |
| BCC-16 | A1 | B1 | C1 | D1 | E1 | F3 | H1 | I1 | J1 | F | returns `2`; stderr `limit must be at least 1, got 0` |
| BCC-17 | A1 | B1 | C1 | D1 | E1 | F1 | H2 | I1 | J1 | H | returns `0`; stdout is `format_results` of `["2-0-0", "2-1-0"]` |
| BCC-18 | A1 | B1 | C1 | D1 | E1 | F1 | H3 | I1 | J1 | H | returns `0`; stdout is `format_results` of `["0-0-0", "1-1-0", "2-0-0", "2-1-0"]` |
| BCC-19 | A1 | B1 | C1 | D1 | E1 | F1 | H4 | I1 | J1 | H | returns `2`; stderr `--can-pop and --cannot-pop both list lead` |
| BCC-20 | A1 | B1 | C1 | D1 | E1 | F1 | H1 | I2 | J1 | I | returns `0`; stdout is `No upgrades match these filters.` |
| BCC-21 | A1 | B1 | C1 | D1 | E1 | F1 | H1 | I3 | J1 | I | returns `0`; stdout is `format_results` of `["0-0-0", "1-1-0"]` |
| BCC-22 | A1 | B1 | C1 | D1 | E1 | F1 | H1 | I1 | J2 | J | with Dart Monkey `0-0-0` inserted, returns `0`; stdout is `format_results` of Super Monkey `["0-0-0", "1-1-0"]`; Dart Monkey is absent |

### Extra non-BCC tests

| Case ID | Covers | Expected result |
|---|---|---|
| EXTRA-1 | `--help` (#41) | `main(["--help"])` raises `SystemExit` with code `0`; stdout contains `load` and `search` |
| EXTRA-2 | `--debug` (#46) | `main(["--debug", "--db", <B4 file>, "search"])` returns `1`; stderr contains `Traceback` and ends with a line containing `file is not a database` |
| EXTRA-3 | no filters (#43) | `main(["--db", DB, "search"])` returns `0`; stdout is `format_results` of all four fixture paths |
| EXTRA-4 | epic example (#43) | `main(["--db", DB, "search", "--cannot-pop", "lead", "--min-pierce", "3", "--sort", "projectile_pierce", "--limit", "5"])` returns `0`; stdout is `format_results` of `["1-1-0"]` |

---

## Table 2: `load`

Fixture: a fake fetch passed to the handler (or monkeypatched over `btd6.etl.pipeline.fetch_tower_module`) that returns the saved Super Monkey module for every tower, so each loads 64 upgrades. Never call the real wiki. Towers load in `MAGIC_TOWERS` order: Super Monkey, Wizard Monkey, Ninja Monkey, Alchemist, Druid. `COUNT(*)` means `SELECT COUNT(*) FROM upgrades` on `NEW_DB` after the call.

Base input: `main(["--db", NEW_DB, "load"])`, with `NEW_DB = tmp_path / "new.db"` not yet created.

### ISP

| Variable | Characteristic | Partition/Block | Representative Value |
|---|---|---|---|
| V1: `--tower` | K: Towers requested | K1 (Base): not given (all magic towers) | — |
| V1: `--tower` | K: Towers requested | K2: one magic tower | `"--tower", "Wizard Monkey"` |
| V1: `--tower` | K: Towers requested | K3: not a magic tower | `"--tower", "Dart Monkey"` |
| V2: fetch | L: Fetch outcome | L1 (Base): every tower succeeds | fake returns the Super Monkey module |
| V2: fetch | L: Fetch outcome | L2: one tower has bad data | fake raises `ValueError("no upgrade data")` for `Alchemist` |
| V2: fetch | L: Fetch outcome | L3: wiki unreachable | fake raises `requests.ConnectionError("connection refused")` on the first call |
| V3: database file | M: State before the call | M1 (Base): missing | `NEW_DB` not created |
| V3: database file | M: State before the call | M2: already loaded | `NEW_DB` after one successful base `load` |

L3 stops the load at the first failed request.

### Base Choice Coverage

| Case ID | K | L | M | Changed characteristic | Expected result |
|---|---|---|---|---|---|
| LOAD-1 | K1 | L1 | M1 | None — All Base | returns `0`; stdout is five lines: `Super Monkey: 64 upgrades`, `Wizard Monkey: 64 upgrades`, `Ninja Monkey: 64 upgrades`, `Alchemist: 64 upgrades`, `Druid: 64 upgrades`; `NEW_DB` exists; `COUNT(*)` is `320` |
| LOAD-2 | K2 | L1 | M1 | K | returns `0`; stdout is `Wizard Monkey: 64 upgrades`; `COUNT(*)` is `64` |
| LOAD-3 | K3 | L1 | M1 | K | `SystemExit.code == 2`; last stderr line starts with `btd6 load: error: argument --tower: invalid choice: 'Dart Monkey'`; `NEW_DB` is not created |
| LOAD-4 | K1 | L2 | M1 | L | returns `1`; stdout is the four success lines without Alchemist; stderr `Alchemist: failed: no upgrade data`; `COUNT(*)` is `256` |
| LOAD-5 | K1 | L3 | M1 | L | returns `1`; stderr `Could not reach the wiki: connection refused`; stdout is empty |
| LOAD-6 | K1 | L1 | M2 | M | returns `0`; stdout is the same five lines as LOAD-1; `COUNT(*)` is still `320` |
