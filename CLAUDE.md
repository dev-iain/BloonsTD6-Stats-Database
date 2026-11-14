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
- Planned: `btd6/db` (SQLite), `btd6/query`, `btd6/cli`; `tests/` mirrors the package
- Data currently covers Super Monkey only. 1.0 scope is magic monkeys; add towers by re-running the fetch with another tower name.
- Upgrade paths are written `X-Y-Z` (e.g. `0-2-3`); the wiki's `_023` codes are converted by `path_from_code`.

## Roadmap
---
Ownership: Iain = SQLite database, JSON -> database, software testing. 
Development is test-driven (ISP/boundary tables for filter inputs).

### 1.0: Filter monkeys based on stats
- [x] Extract wiki JSON into flat stat rows (`extract_row`)
- [ ] Test suite: ISP tables, factory_boy fixtures, hypothesis, mutmut
- [ ] JSON -> SQLite loader with an efficient relational schema
- [ ] Querying: search monkeys and stats (magic monkeys only)
- [ ] CLI-based interaction

### 2.0: Round information and rankings
- [ ] Round data in the database (up to round 40)
- [ ] Expected income per round from pops (excludes monkeys that affect cash generation, positive or negative)
- [ ] Suggested monkey for a round: highest rank in pierce, damage, etc. (pandas)
- [ ] Best bang for buck: highest damage per dollar
- [ ] Ranking based on filters
- [ ] Mod to capture game data for an LLM/MCP (MelonLoader): round, current money, current towers
- [ ] Stats per attack: damage, pierce, damage type (shatter, explosive, tack), projectile speed, range

### 3.0: BTD6 Agent
- [ ] Takes round and total money as input
- [ ] Subagent determines round information, then recommends towers from the statistics
- [ ] Round 63 (camo lead and ceramic heavy) should recommend pierce
- [ ] Round 40 (has a MOAB) should recommend high-damage MOAB options
