# BTD6 Tower Stats Database

A database of Bloons Tower Defense 6 tower stats, pulled from the BTD6 wiki, with a command-line search. Version 1.0 covers the Magic towers: Super Monkey, Wizard Monkey, Ninja Monkey, Alchemist and Druid.

Roadmap:
- **1.0:** filter upgrades by stats from the command line (this release).
- **2.0:** round data, expected income per round, and tower rankings.
- **3.0:** an agent that recommends towers for a given round and amount of money.

## Requirements and setup

- Python 3.14
- [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

## Build the database

`load` downloads each Magic tower from the BTD6 wiki, so it needs network access. It writes `btd6.db` in the project folder (use `--db PATH` before the command to choose another file). Running it again replaces the data instead of duplicating it.

```bash
uv run python -m btd6 load
```

```text
Super Monkey: 64 upgrades
Wizard Monkey: 64 upgrades
Ninja Monkey: 64 upgrades
Alchemist: 64 upgrades
Druid: 64 upgrades
```

Load only some towers with `--tower` (repeatable): `uv run python -m btd6 load --tower "Wizard Monkey"`.

## Search

`search` looks through the Magic towers. Filters combine with AND.

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

## Project layout

| Path | Contents |
|---|---|
| `btd6/etl/` | wiki fetch, crosspath resolution, stat extraction, refresh pipeline |
| `btd6/db/` | SQLite connection, migrations, seeding and loader |
| `btd6/query.py` | `search_upgrades` and `UpgradeFilters` |
| `btd6/cli.py` | the `load` and `search` commands |
| `tests/` | pytest suite; ISP/BCC tables in `tests/isp-tables/` |
| `docs/` | [schema](docs/schema.md) and [query contract](docs/queries.md) |

## Contributing

- Test first: write the ISP and BCC tables in `tests/isp-tables/`, then the failing tests, then the code.
- Follow the style rules in `CLAUDE.md`: type hints with `from __future__ import annotations`, functions of at most 30 lines, descriptive names, no comments used to organize code.
- One pull request per issue (or per epic, when agreed), with `Closes #N` in the description.
