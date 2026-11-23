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
- `btd6/etl/extract.py`: flattens a resolved upgrade into a stats row (`extract_row`), `DAMAGE_TYPES` bitmask table
- `data.csv`: current extractor output (64 upgrades), used as a regression fixture
- `btd6/db/connection.py`: `connect` (default `btd6.db`, foreign keys on, `sqlite3.Row`); `btd6/db/seed.py`: `seed_lookup_tables` from `DAMAGE_TYPES`, `initialize_database`; `btd6/db/__init__.py`: `apply_migrations` (numbered scripts in `btd6/db/migrations/`, tracked by `PRAGMA user_version`); schema decisions in `docs/schema.md`
- `btd6/query.py`: `UpgradeFilters` and `search_upgrades` (contract in `docs/queries.md`)
- `btd6/formatting.py`: shared cell formatting
- `btd6/api/`: FastAPI app (`create_app`) serving `/api/upgrades`, `/api/rankings`, `/api/damage-types` and the `frontend/` JS UI; `params.py` holds the pure `form_to_filters`/`form_to_search_options`/`rows_to_cells`; see `docs/web.md`
- `btd6/cli.py`: argparse entry point (`python -m btd6`); commands `load`, `search`, `rank` and `serve`
- `btd6/ranking.py`: `add_metrics`, `rank_upgrades` (formulas in `docs/ranking.md`)
- `btd6/costs.py`: `total_cost`; `btd6/db/cost_loader.py`: `load_costs`; `fetch_costs` in `btd6/etl/fetch.py`; migration `002_costs` adds the costs tables
- Planned: `btd6/db/loader.py`, refresh pipeline; `tests/` mirrors the package
- Data currently covers Super Monkey only. 1.0 scope is magic monkeys; add towers by re-running the fetch with another tower name.
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
- [ ] Round data in the database (up to round 40)
  - only stores count and bloon type; needs to have income data calculations (how much each round makes in total when popping all bloons)
- [ ] Expected income per round from pops (excludes monkeys that affect cash generation, positive or negative)
- [ ] Best bang for buck: highest damage per dollar
  - Must come up with formula to calculate damage per second based on attack rate, projectile speed, etc to do this.
- [ ] Mod to capture game data for an LLM/MCP (MelonLoader): round, current money, current towers 

### 3.0: BTD6 Agent
- [ ] Takes round and total money as input
- [ ] Subagent determines round information, then recommends towers from the statistics
- [ ] Round 63 (camo lead and ceramic heavy) should recommend pierce
- [ ] Round 40 (has a MOAB) should recommend high-damage MOAB options
- [ ] Suggested monkey for a round: highest rank in pierce, damage, etc. (pandas)