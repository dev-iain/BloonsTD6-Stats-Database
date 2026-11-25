# BTD6 Tower Stats Database & Agent
---
Database for compiling tower stats from Bloons Tower Defense 6, as well as an agent that provides recommendations on towers for the given round.

## Stack
---
- Language: Python 3.14
- Database: SQLite
- Data: Pandas, JSON
- Testing: pytest, factory_boy, hypothesis, mutmut
- Linting: Ruff (linter + formatter)
- Package Manager: uv

## Conventions
---
### Code style
- Type hints on all function signatures. Use `from __future__ import annotations`
- Maximum function length: 30 lines. Extract helpers with descriptive names. 
- No mutable default arguments. Use `None` with `if arg is None: arg = []`
- Use human-understandable variable names. Most variable names should not be less than 4 characters. 
- Organize code by functionality. 
- Whenever a NULL appears in the database or extracted rows, check the original JSON for that tower (fetch the wiki module or read the tower's resolved JSON) to find out why, and record the cause in `docs/data-notes.md`. A NULL may come from `extract_row` reading a first `_order` entry that is not the main attack, not from missing data.
- Do not use comments to organize code. If you have numerous methods for one specific feature, which in total sums to 100+ lines of code, use regions.

## Commands
---
- Tests: `uv run pytest`
- Lint + format: `uv run ruff check . && uv run ruff format .`
- Mutation testing: `uv run mutmut run`
- Refresh data: `uv run python -c "from btd6.etl.fetch import write_resolved_json; write_resolved_json('Super Monkey')"`
- Rebuild CSV: `uv run python -c "from btd6.etl.extract import export_csv; export_csv()"`

## Architecture
---
- `btd6/etl/fetch.py`: wiki API fetch, crosspath resolution (`resolve_all_codes`) -> `data.json` (gitignored)
- `btd6/etl/extract.py`: flattens a resolved upgrade into a stats row (`extract_row`), `DAMAGE_TYPES` bitmask table; round and bloon flattening: `extract_round_rows`, `extract_bloon_rows` (Cargo strings -> typed rows, `id` is stored as `name`) and `split_bloon_name` (`BfbFortified` -> base, camo, regrow, fortified)
- `data.csv`: current extractor output (64 upgrades), used as a regression fixture
- `btd6/db/connection.py`: `connect` (default `btd6.db`, foreign keys on, `sqlite3.Row`); `btd6/db/seed.py`: `seed_lookup_tables` from `DAMAGE_TYPES`, `initialize_database`; `btd6/db/__init__.py`: `apply_migrations` (numbered scripts in `btd6/db/migrations/`, tracked by `PRAGMA user_version`); schema decisions in `docs/schema.md`
- `btd6/query.py`: `UpgradeFilters` and `search_upgrades` (contract in `docs/queries.md`)
- `btd6/formatting.py`: shared cell formatting
- `btd6/api/`: FastAPI app (`create_app`) serving `/api/upgrades`, `/api/rankings`, `/api/damage-types` and the `frontend/` JS UI; `params.py` holds the pure `form_to_filters`/`form_to_search_options`/`rows_to_cells`; see `docs/web.md`
- `btd6/cli.py`: argparse entry point (`python -m btd6`); commands `load`, `search`, `rank`, `serve` and `start` (loads the db if missing or `--refresh`, then serves; `--game`, `--no-browser`)
- `btd6/launcher.py`: `browser_url`, `open_uri` (per-platform), `launch_game` (Steam URI), `wait_for_port`, `open_browser_when_ready`; `start.sh`/`start.bat` wrap `uv sync` + `python -m btd6 start`
- `btd6/ranking.py`: `add_metrics`, `rank_upgrades` (formulas in `docs/ranking.md`)
- `btd6/costs.py`: `total_cost`; `btd6/db/cost_loader.py`: `load_costs`; `fetch_costs` in `btd6/etl/fetch.py`; migration `002_costs` adds the costs tables
- `btd6/db/round_loader.py`: `load_bloons` (upsert by name, keeps ids), `load_rounds` (replaces rounds 1-100 and their groups); `fetch_bloons` in `btd6/etl/fetch.py` (paged Cargo `btd6_bloons`, spaces in keys become `_`); `btd6/rounds.py`: `get_round`, `get_round_summary`; migration `003_rounds` adds `bloons`, `rounds`, `round_groups`; `python -m btd6 rounds --round N` (or `--from A --to B`) prints a round; `load` also loads bloons and rounds unless `--no-rounds`; known data quirks in `docs/data-notes.md`
- `btd6/recommend.py`: `recommend(connection, round, money, difficulty, limit, horizon, owned, one_per_tower)` -> `Recommendation`s (eligibility from `round_threats`; score is a decay-weighted fit over rounds N..N+horizon-1 with pierce capped by `crowd_density` x range; picks that leak a later window round (`fails_camo_at_24`) sort last; `owned` (`OwnedTower`) covers needs and adds upgrade candidates priced as the difference (`upgrade_from`); `one_per_tower` keeps the best row per tower; rules in `docs/recommend.md`); `python -m btd6 recommend --round N --money X [--horizon H] [--one-per-tower]`, `GET /api/recommendations`, Recommend tab in the web UI
- `btd6/agent/`: LLM advisor (epic #125, contract in `docs/agent.md`): `schemas.py` `TOOL_SCHEMAS`; `tools.py` `call_tool` (wrappers over threats/search/rank/recommend/costs, structured errors, no NaN); `client.py` `OpenAICompatibleClient`, `client_from_environment` (free Gemini tier by default; key from `GEMINI_API_KEY`, then `.env`, then `gemini_api_key.txt` via `find_api_key`/`API_KEY_FILES`; `start` writes the txt template); `picks.py` `parse_picks` (up to `MAX_PICKS` = 5, each with a reason); `loop.py` `run_agent` (tool loop, iteration cap). `python -m btd6 agent --round N --money X`, `GET /api/agent` and the Ask the agent section of the Recommend tab; offline evals in `tests/agent_evals/`, live ones with `-m live_agent` (deselected by default)
- `btd6/game_state.py`: live game state contract (`docs/game-state.md`): `parse_game_state`, `save_game_state`/`load_game_state` (30 s staleness), `state_summary`, `fake_game_state`; `POST`/`GET /api/game-state` (`create_app(db, state_path, clock)`), `recommend --live`/`agent --live` (`--max-age`), `fake-state`, `game-state`; agent tool `get_game_state` (`LIVE_TOOL_SCHEMAS`, only in live runs)
- `mod/`: C# MelonLoader/Mod Helper mod (`docs/mod.md`, `mod/README.md`); `GameStateReporter.Core` is game-independent and tested with `dotnet test mod/GameStateReporter.Tests`; `dotnet build mod/GameStateReporter` needs the game with MelonLoader and copies the DLL into `Mods/`
- Planned: `btd6/db/loader.py`, refresh pipeline; `tests/` mirrors the package
- Data covers the five magic monkeys plus Dart Monkey, Boomerang Monkey, Bomb Shooter, Sniper Monkey and Ice Monkey (64 upgrades each; `EXTRA_TOWERS`/`KNOWN_TOWERS` in `btd6/etl/towers.py`, loaded with `load --tower NAME`, category from Cargo; `search`/`rank --tower NAME` skip the default Magic filter) plus bloons and rounds 1-100; `data.csv` is Super Monkey only. 1.0 scope is magic monkeys; add towers by re-running the fetch with another tower name.
- Upgrade paths are written `X-Y-Z` (e.g. `0-2-3`); the wiki's `_023` codes are converted by `path_from_code`.

## Roadmap
---
Ownership: Iain = SQLite database, JSON -> database, software testing. 
Development is test-driven (ISP/boundary tables for filter inputs).

### 1.0: Filter monkeys based on stats
- [X] Extract wiki JSON into flat stat rows (`extract_row`)
- [X] Test suite: ISP tables, factory_boy fixtures, hypothesis, mutmut
- [X] JSON -> SQLite loader with an efficient relational schema
- [X] Querying: search monkeys and stats (magic monkeys only)
- [X] CLI-based interaction

### 2.0: Round information and rankings, in order of priority
- [X] Implement web UI (FastAPI + JS frontend, replaced Tkinter)
- [X] Round data in the database (up to round 40)
  - only stores count and bloon type; needs to have income data calculations (how much each round makes in total when popping all bloons)
- [X] Expected income per round from pops (excludes monkeys that affect cash generation, positive or negative)
- [X] Best bang for buck: highest damage per dollar
  - Must come up with formula to calculate damage per second based on attack rate, projectile speed, etc to do this.
- [X] Mod to capture game data for an LLM/MCP (MelonLoader): round, current money, current towers
  - phases 1-4 done (contract, API + web autofill, CLI/agent `--live`, C# mod), checked in game under Proton; MCP server (phase 5) optional 

### 3.0: BTD6 Agent
- [X] Takes round and total money as input
- [X] Subagent determines round information, then recommends towers from the statistics (free Gemini tool loop, epic #125)
- [X] Round 63 (camo lead and ceramic heavy) should recommend pierce (live eval `round63_pierce`)
- [X] Round 40 (has a MOAB) should recommend high-damage MOAB options (live eval `round40_moab`)
- [X] Suggested monkey for a round: highest rank in pierce, damage, etc. (pandas): deterministic recommender, epic #119