# Live game state contract

The `mod/` MelonLoader mod (GameStateReporter) posts a JSON snapshot of the running game to
`POST /api/game-state`. The server validates it with `btd6.game_state.parse_game_state` and
saves it to `game_state.json` (project root, gitignored; `--state-file` overrides). The CLI
(`recommend --live`, `agent --live`, `game-state`) and the agent tool `get_game_state` read that
file, so they work without the server running. `python -m btd6 fake-state` writes the same file
without the game.

## Payload (version 1)

```json
{
  "version": 1,
  "round": 40,
  "cash": 5123.7,
  "lives": 150,
  "difficulty": "Medium",
  "mode": "Standard",
  "map": "Monkey Meadow",
  "towers": [
    {"base_id": "DartMonkey", "tiers": [0, 2, 3]},
    {"base_id": "BananaFarm", "tiers": [2, 0, 0]}
  ]
}
```

| Key | Type | Rule |
|---|---|---|
| `version` | int | must be `1` |
| `round` | int | `>= 1`; the round being played or about to start (game's zero-based round + 1) |
| `cash` | number | `>= 0`; floored to an int `money` |
| `lives` | number | `>= 0`; floored to an int |
| `difficulty` | str | `Easy`, `Medium` or `Hard` (case-insensitive) |
| `mode` | str | any non-empty string; `Impoppable` turns difficulty into `impoppable` |
| `map` | str | any string |
| `towers` | list | each item has `base_id` (non-empty str) and `tiers` (three ints, each 0-5) |

Booleans are not accepted where a number is expected. Missing keys, wrong types or out-of-range
values raise `GameStateError` (HTTP 422 from the API).

## HTTP endpoints

Served by `create_app(database_path, state_path, clock)` (`btd6/api/app.py`); `serve` passes `--state-file`.

| Endpoint | Response |
|---|---|
| `POST /api/game-state` | Body is a version 1 payload. It is validated, saved with `received_at = clock()` and returned as `state_summary`. Invalid payloads, and bodies that are not a JSON object, are 422 (`{"error": ...}`); nothing is written |
| `GET /api/game-state` | The stored state as `state_summary` with the default 30 s limit. A stale state is still returned, with `stale: true`. No file is 404; a corrupt file is 422 |

`state_summary(stored, now, max_age_seconds=30)` returns `round`, `money`, `lives`, `difficulty` (recommender value, e.g. `impoppable`), `mode`, `map`, `towers` (`base_id`, `tower_name`, `path`, `known`), `received_at`, `age_seconds` and `stale` (age over the limit; never with `None`). The agent's `get_game_state` tool returns the same dict.

## Consumers

- Web UI: the Recommend tab's **Use live game** toggle polls `GET /api/game-state` every 2 s, fills round, money and difficulty, and re-runs the recommendation when they change. It shows `Live · round N · $X · K towers · updated Ns ago`, `Game state is stale ...` or `No game connected ...`.
- CLI: `recommend --live` and `agent --live` read round, money and difficulty from the file instead of `--round`/`--money`/`--difficulty` (combining them is a usage error, exit 2). `--max-age S` sets the staleness limit (`0` turns it off). A missing or stale state exits with code 1. `recommend --live` prints `Live game: round N, $X, difficulty D` above the usual table.
- Agent: with `--live`, the opening request lists the owned towers and the `get_game_state` tool is offered (`docs/agent.md`).

## Normalised fields

- `difficulty_from_game(difficulty, mode)` returns the recommender's difficulty: `impoppable` when
  `mode` is `Impoppable` (any case), otherwise the lower-cased difficulty. CHIMPS is played on Hard
  and maps to `hard`.
- `tower_name_from_game_id(base_id)` maps a game id such as `DartMonkey` to the database name
  `Dart Monkey` for every tower in `KNOWN_TOWERS`; other ids give `None`, and the tower is kept with
  `known = False`.
- `tiers_to_path([0, 2, 3])` returns `0-2-3`.

## Stored file and staleness

The stored file is the payload plus `received_at` (ISO 8601 UTC), set when the state is saved.
`load_game_state(path, max_age_seconds, now)` raises `NoGameStateError` when the file is missing
and `StaleGameStateError` when `now - received_at` is more than `max_age_seconds` (default
`DEFAULT_MAX_AGE_SECONDS = 30`; `None` turns the check off). The mod re-sends an unchanged snapshot
every 5 seconds as a heartbeat, so a state older than 30 seconds means the game is closed or the
mod is not running.
