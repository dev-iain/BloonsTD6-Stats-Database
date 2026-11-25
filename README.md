# BTD6 Tower Stats Database

A database of Bloons Tower Defense 6 tower stats, pulled from the BTD6 wiki, with a command-line and web interface, round and income data, tower rankings, a recommender, an LLM advisor and a mod that reports the live game. It covers ten towers: the five Magic towers (Super Monkey, Wizard Monkey, Ninja Monkey, Alchemist, Druid) plus Dart Monkey, Boomerang Monkey, Bomb Shooter, Sniper Monkey and Ice Monkey.

Releases:
- **1.0:** filter upgrades by stats from the command line.
- **2.0:** web UI, round data, expected income per round, tower rankings and the live-game mod.
- **3.0:** recommendations for a given round and amount of money, from a deterministic recommender and an LLM advisor (current).

## Requirements and setup

- Python 3.14
- [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

## Quick start

One command installs the dependencies, builds `btd6.db` from the wiki on the first run, starts the web UI and opens it in your browser:

```bash
./start.sh            # Linux / macOS
start.bat             # Windows (or double-click it)
```

Options are passed through to `python -m btd6 start`:

| Option | Meaning |
|---|---|
| `--game` | also launch BTD6 through Steam (`steam://rungameid/960090`), so the mod can report to the server |
| `--refresh` | download the data from the wiki again before serving |
| `--no-browser` | do not open a browser tab |
| `--host H`, `--port N` | where to serve (defaults `127.0.0.1` and `8000`) |

Press Ctrl+C to stop. If the first download fails, the half-built database is removed so the next start tries again. The sections below cover each command on its own.

## Build the database

`load` downloads each Magic tower, the bloon stats and rounds 1-100 from the BTD6 wiki, so it needs network access. It writes `btd6.db` in the project folder (use `--db PATH` before the command to choose another file). Running it again replaces the data instead of duplicating it.

```bash
uv run python -m btd6 load
```

```text
Super Monkey: 64 upgrades
Wizard Monkey: 64 upgrades
Ninja Monkey: 64 upgrades
Alchemist: 64 upgrades
Druid: 64 upgrades
Rounds: 100 rounds, 1234 groups
```

Load only some towers with `--tower` (repeatable): `uv run python -m btd6 load --tower "Wizard Monkey"`. Add `--no-rounds` to skip the bloons and rounds (no round download, existing rounds stay untouched). If only the bloons or rounds step fails, the towers are still loaded and the error is printed as `Bloons: failed: ...` or `Rounds: failed: ...`.

## Search

`search` looks through every loaded tower (use `--tower NAME` to pick one). Filters combine with AND.

| Option | Meaning |
|---|---|
| `--can-pop PROP` / `--cannot-pop PROP` | can (or cannot) pop `lead`, `black`, `white`, `purple`, `glass` or `frozen`; repeatable |
| `--min-pierce N`, `--min-damage N`, `--min-range N`, `--min-speed N` | at least this value |
| `--damage-type NAME` | exact damage type, e.g. `Plasma` |
| `--camo` / `--no-camo` | can (or cannot) hit camo bloons |
| `--sort COLUMN` | `range`, `attack_rate`, `projectile_damage`, `projectile_pierce`, `projectile_speed`, `projectile_count` or `ability_cooldown`, highest first |
| `--limit N` | show at most N upgrades |

Upgrades that cannot pop lead, with at least 3 pierce, highest pierce first:

```bash
uv run python -m btd6 search --cannot-pop lead --min-pierce 3 --sort projectile_pierce --limit 5
```

```text
        tower  path   type damage pierce range speed rate camo lead black white purple glass frozen
Wizard Monkey 3-0-1 Energy      3     12    60   400 0.55   no   no   yes   yes     no    no    yes
Wizard Monkey 0-0-1 Energy      1      8    40   400  1.1   no   no   yes   yes     no    no    yes
Wizard Monkey 0-0-2 Energy      1      8    50   400  1.1  yes   no   yes   yes     no    no    yes
Wizard Monkey 0-0-3 Energy      1      8    60   400  1.1  yes   no   yes   yes     no    no    yes
Wizard Monkey 0-0-4 Energy      1      8    60   400  1.1  yes   no   yes   yes     no    no    yes
```

Plasma upgrades that can hit camo, longest range first:

```bash
uv run python -m btd6 search --damage-type Plasma --camo --sort range --limit 3
```

```text
        tower  path   type damage pierce range speed   rate camo lead black white purple glass frozen
 Super Monkey 0-4-2 Plasma      1      7    75   350  0.045  yes  yes   yes   yes     no    no    yes
Wizard Monkey 4-0-2 Plasma      6      7    70   200  0.275  yes  yes   yes   yes     no    no    yes
Wizard Monkey 5-0-2 Plasma      8     11    70   200 0.1375  yes  yes   yes   yes     no    no    yes
```

Columns: `type` is the damage type, `rate` is seconds between attacks (lower is faster), `camo` is whether it hits camo bloons, and `lead` to `frozen` say which bloon properties it can pop. `-` means the wiki has no value.

Mistakes print one line and exit with a non-zero code (add `--debug` before the command to see the full error):

```text
$ uv run python -m btd6 search --damage-type Bogus
Unknown damage type "Bogus". Valid types: Acid, Cold, Energy, Explosion, Fire, Frigid, Glacier, Normal, Plasma, Sharp, Shatter, Unknown

$ uv run python -m btd6 search --limit 0
limit must be at least 1, got 0

$ uv run python -m btd6 --db missing.db search
Database not found at missing.db. Run "python -m btd6 load" first.
```

## Rankings

`rank` orders upgrades by damage per second or per dollar. It accepts the same filters as `search` (except `--sort`) plus `--metric` (`dps`, `dollar`, `pierce-dollar`; default `dollar`), `--difficulty` (`easy`, `medium`, `hard`, `impoppable`; default `medium`) and `--limit`.

```bash
uv run python -m btd6 rank --metric dps --difficulty hard --can-pop lead --limit 5
```

The table has the columns rank, tower, path, cost, DPS and damage per dollar. Formulas are in `docs/ranking.md`. Limitations:

- Only the first attack and its first projectile are read, so towers with several attacks (Wizard, Ninja, Alchemist, Druid) are under-counted.
- Abilities, buffs to other towers, damage-over-time and bonus damage to specific bloons are not included.
- Pierce-weighted metrics assume every projectile uses its full pierce.
- Range, projectile speed and lifespan are not part of any metric.
- Upgrades with unknown damage, attack rate or cost (costs not loaded) rank last.

## Round income

`rounds --round N` also prints the round's threat summary (share of RBE per bloon property, camo, regrow and MOAB, and mean layers; see `docs/threats.md`). `income` shows the cash earned from popping every bloon in a round plus the end-of-round bonus, using the loaded round data and income multipliers. Give exactly one of `--round N` (one line) or `--up-to N` (a table for rounds 1 to N with a running total). Run `load` first; a round outside the loaded range exits with code 2.

```bash
uv run python -m btd6 income --round 40
```

```text
Round 40: $381 pop cash + $140 end bonus = $521
```

```bash
uv run python -m btd6 income --up-to 5
```

```text
 round pop cash end bonus total running total
     1       20       101   121           121
     2       35       102   137           258
     3       35       103   138           396
     4       71       104   175           571
     5       59       105   164           735
```

## Web UI

```bash
uv run python -m btd6 serve
uv run python -m btd6 --db path/to/btd6.db serve --port 9000
```

Then open `http://127.0.0.1:8000`. `--db PATH` works the same as for `search`; `--host` and `--port` default to `127.0.0.1` and `8000`.

- **Search**: the same filters as the `search` command, plus a name box (case-insensitive substring), a damage type dropdown, a sort dropdown and a limit.
- **Rankings**: rank upgrades by damage per dollar, DPS or pierce-weighted damage per dollar, for any difficulty.
- **Rounds**: a round's summary, income, bloon totals and spawn order.
- **Recommend**: affordable upgrades for a round and amount of money, with an optional live-game mode.
- Follows your system light or dark setting.

The page is served by a small JSON API (`/api/upgrades`, `/api/rankings`, `/api/rounds`, `/api/recommendations`, `/api/game-state`, ...). The endpoints and layout are in [docs/web.md](docs/web.md).

## Agent (LLM advisor)

`agent` asks an LLM for advice on what to buy for a round. The model can only answer through tools backed by this database: round threats, search, rankings, the recommender and costs. Every number it states comes from a tool result. The design, tool schemas and system prompt are in [docs/agent.md](docs/agent.md).

It uses the **free tier of the Gemini API** through Google's OpenAI-compatible endpoint, so no paid key is needed.

1. Install and build the database:

   ```bash
   uv sync
   uv run python -m btd6 load
   ```

2. Get a free key at <https://aistudio.google.com/apikey> (a Google account is enough, no card). Put it in a `.env` file in the repo root. `.env` is gitignored; never put the key in a tracked file.

   ```bash
   printf 'GEMINI_API_KEY=your-key-here\n' > .env
   chmod 600 .env
   ```

   The key is read from the environment only. `uv run --env-file .env` loads the file for one command. To skip the flag, run `set -Ux UV_ENV_FILE .env` (fish) or `export UV_ENV_FILE=.env` (bash/zsh) once. Exporting `GEMINI_API_KEY` in your shell also works.

3. Ask for a recommendation:

   ```bash
   uv run --env-file .env python -m btd6 agent --round 63 --money 5000
   uv run --env-file .env python -m btd6 agent --round 40 --money 20000 --difficulty hard
   ```

   The output is a short explanation of the round's threats and why the picks fit, ending with a `Picks:` block (`- <tower> <X-Y-Z> $<cost>`, or `- none` when nothing affordable can handle the round). A real run (`gemini-3.5-flash-lite`, about 2 seconds):

   ```text
   Round 63 features heavy ceramic rushes with a high total Red Bloon Equivalent (14,413) and some lead
   properties, but no camo, regrow, or MOAB-class bloons. High pierce and lead-popping power are essential
   to clean up the massive density of bloons. The Boomerang Monkey (4-0-2) fits this exceptionally well
   with its high projectile pierce of 60.0 and ability to pop lead within your $5000 budget.

   Picks:
   - Boomerang Monkey 4-0-2 $3795
   ```

Options:

- `--difficulty`: `easy`, `medium` (the default), `hard` or `impoppable`.
- `--max-iterations K`: stop after K model calls without a final answer. The default is 8.
- Optional environment variables:
  - `BTD6_AGENT_MODEL`: the model. The default is `gemini-3.5-flash-lite`. `gemini-3.8-flash` is also free but is often overloaded (HTTP 503).
  - `BTD6_AGENT_BASE_URL`: any other OpenAI-compatible provider, such as Groq or OpenRouter free models. Put that provider's key in `GEMINI_API_KEY`.
- A missing key exits with code 2 and a message saying how to get one.

Cost per run is **$0** on the free tier. A run makes about 3 to 5 model calls. The free tier is rate-limited per project. A busy or rate-limited model (HTTP 429 or 503) or a timeout is retried twice. If it still fails, the CLI says so and exits with code 1. Wait a minute or switch `BTD6_AGENT_MODEL`. Google may use free-tier prompts to improve its products, so do not send anything private.

Limitations:

- Stats come from each upgrade's first (main) attack only. Abilities, buffs and sub-towers are not modelled.
- Only the towers loaded into the database can be picked (the ten in `KNOWN_TOWERS`).
- The model chooses and explains, but it can still word things badly. Check the `Picks:` block against `recommend`.

Evaluations: `uv run pytest` runs the offline evals in `tests/agent_evals/` with a scripted model. `uv run pytest -m live_agent` runs the same scenarios (rounds 40, 63, a camo round, low money and no round data) against the real model. It needs `GEMINI_API_KEY` and `btd6.db`.

## Live game (mod)

The `mod/` folder holds a BTD6 mod (MelonLoader + BTD Mod Helper, Windows and Linux/Proton) that posts the running game's round, cash, lives, difficulty and towers to `serve`. Setup is in [mod/README.md](mod/README.md); the contract is [docs/game-state.md](docs/game-state.md).

```bash
uv run python -m btd6 serve                 # receives POST /api/game-state from the mod
uv run python -m btd6 game-state            # show the stored state
uv run python -m btd6 recommend --live      # round, money and difficulty from the game
uv run --env-file .env python -m btd6 agent --live
```

- In the web UI, tick **Use live game** on the Recommend tab. It refreshes every 2 seconds and re-runs the recommendation when the round, cash or difficulty changes.
- Without the game, `uv run python -m btd6 fake-state --round 63 --money 8000 --tower "Dart Monkey:0-2-3"` writes the same file.
- A state older than 30 seconds is stale (the game is closed or in the menu); `--max-age S` changes the limit and `--max-age 0` turns it off.
- `agent --live` also tells the model which towers you own and gives it a `get_game_state` tool.
- Offline/solo play only: Ninja Kiwi can flag modded online play.

## Tests, linting and mutation testing

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run ruff format .
```

```bash
uv run mutmut run
```

```bash
dotnet test mod/GameStateReporter.Tests   # C# mod logic, no game needed
```

## Project layout

| Path | Contents |
|---|---|
| `btd6/etl/` | wiki fetch, crosspath resolution, stat extraction, refresh pipeline |
| `btd6/db/` | SQLite connection, migrations, seeding and loader |
| `btd6/query.py` | `search_upgrades` and `UpgradeFilters` |
| `btd6/cli.py` | every command: `start`, `load`, `search`, `rank`, `serve`, `rounds`, `income`, `recommend`, `agent`, `fake-state`, `game-state` |
| `btd6/formatting.py` | result columns and cell formatting shared by the CLI and the UI |
| `btd6/api/` | FastAPI app and request parsing behind the web UI |
| `frontend/` | the JS web UI (HTML, CSS, ES module) |
| `mod/` | the C# BTD6 mod that reports the live game ([mod/README.md](mod/README.md)) |
| `tests/` | pytest suite; ISP/BCC tables in `tests/isp-tables/` |
| `docs/` | [schema](docs/schema.md), [query contract](docs/queries.md) and [web UI and API](docs/web.md) |

## Contributing

- Test first: write the ISP and BCC tables in `tests/isp-tables/`, then the failing tests, then the code.
- Follow the style rules in `CLAUDE.md`: type hints with `from __future__ import annotations`, functions of at most 30 lines, descriptive names, no comments used to organize code.
- One pull request per issue (or per epic, when agreed), with `Closes #N` in the description.
