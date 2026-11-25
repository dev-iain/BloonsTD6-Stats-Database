# Web UI and API

Run with `uv run python -m btd6 serve` (honors `--db`; `--host` defaults to `127.0.0.1`, `--port` to `8000`), then open `http://127.0.0.1:8000`. The command exits 1 with the usual "Database not found" message when the database file is missing.

## Why a local server

The UI is plain JS served by the same Python process that owns SQLite. The future MelonLoader mod can `POST` game state to this server, and the planned agent can read from it, so there is one backend for all three. No Electron or build step is needed; a native-window wrapper (pywebview or Tauri) can load the same URL later.

## Endpoints

All responses are JSON. Errors are `{"error": "<message>"}`: `QueryError` (including an unloaded round number) gives 422, no round data loaded gives 404, a missing database gives 503.

| Endpoint | Query parameters | Response |
|---|---|---|
| `GET /api/upgrades` | `name`, `min_range`, `min_pierce`, `min_damage`, `min_speed`, `damage_type`, `camo` (`either`/`yes`/`no`), one of `lead`/`black`/`white`/`purple`/`glass`/`frozen` (`any`/`can`/`cannot`), `sort`, `limit` | `{"rows": [...]}` raw `search_upgrades` columns |
| `GET /api/rankings` | the filters above, plus `metric` (`dps`, `damage_per_dollar`, `pierce_damage_per_dollar`), `difficulty`, `limit` | `{"rows": [...]}` ranked, with `total_cost`, `dps`, `damage_per_dollar` (`null` for missing values) |
| `GET /api/damage-types` | none | `{"damage_types": [...]}` |
| `GET /api/rounds` | none | `{"first": 1, "last": N}` loaded round range (both `null` when empty) |
| `GET /api/rounds/{n}` | none | `{"round", "summary", "composition", "groups", "income", "threats"}`: `summary` is `RoundSummary` (totals plus `has_moab`/`has_camo`/`has_lead`/`has_ceramic`), `composition` the bloon totals (groups merged by bloon and modifiers, with `count` and `total_rbe`, largest RBE first), `groups` the spawn order, `income` is `pop_cash`, `end_bonus`, `total`, `cumulative` or `null` when income data is not loaded; `threats` is `RoundThreats` from `btd6/threats.py` (`total_rbe`, `unknown_groups`, `property_share` per `lead/black/white/purple/glass/frozen`, `camo_share`, `regrow_share`, `moab_share`, `mean_layers`; formulas in `docs/threats.md`) |
| `POST /api/game-state` | JSON body (version 1 payload, `docs/game-state.md`) | The saved state as `state_summary`; invalid body 422 |
| `GET /api/game-state` | none | `state_summary` of the stored state (`round`, `money`, `lives`, `difficulty`, `mode`, `map`, `towers`, `received_at`, `age_seconds`, `stale`); 404 when there is none |
| `GET /api/health` | none | `{"app": "btd6", "pid": <server process id>}`. Used by `start` to find and replace an advisor that is already running (see Restarting) |
| `GET /api/recommendations` | `round` (required int), `money` (required int, 0 or more), `difficulty` (`easy`/`medium`/`hard`/`impoppable`, default `medium`), `limit` (optional, at least 1), `horizon`, `one_per_tower`, repeated `owned` (see `docs/recommend.md`, Callers) | `{"rows": [...]}` in rank order, each with every `Recommendation` field (`tower_name`, `path`, `total_cost`, `upgrade_from`, `score`, `dps`, `moab_dps`, `pierce_weighted_dps`, `projectile_pierce`, `effective_pierce`, `first_leak_round`, `reasons`; see `docs/recommend.md`). Bad input and an unloaded round are `QueryError` (422), no round data 404, missing database 503 |

Parameters are parsed by `btd6.api.params.form_to_filters` and `form_to_search_options`. Each request opens its own SQLite connection.

## Layout

- `btd6/api/app.py`: `create_app(database_path, state_path=None, clock=None)`, routes, error handlers, static mount. `state_path` defaults to `game_state.json` in the project root; `clock` (UTC `datetime` factory) is for tests.
- `frontend/`: `index.html`, `style.css`, `app.js` (ES module, no dependencies). Served at `/` and `/static/`. Table cells are set with `textContent`, never `innerHTML`.
- Search, Rankings, Rounds and Recommend tabs are live. The Rounds tab shows Summary and Income cards (money in green), then a bloon totals table and the spawn order table.
- The Recommend tab takes round (bounded by `/api/rounds`), money, difficulty and an optional limit, calls `/api/recommendations` and `/api/rounds/{n}`, and shows Round threats and Bloon properties cards (shares as percentages, mean layers) above a table of rank, tower, path, cost, score and reasons. API errors show in the status line; no rows shows "No affordable upgrade can handle this round."
- **One per tower** (Recommend tab) keeps the best row per tower (`one_per_tower=true`). The table has an **Upgrade from** column for upgrades of owned towers.
- **Use live game** (Recommend tab) sends the known owned towers as `owned` params (`docs/recommend.md`, Owned towers) and polls `GET /api/game-state` every 2 s (`LIVE_POLL_MS`) while ticked, makes round and money read-only, fills round, money and difficulty from a fresh state and submits the form when any of them changed. A stale or missing state only updates the live status line.

## Restarting

Running `./start.sh` / `start.bat` (`python -m btd6 start`) again **replaces** an advisor that is already running on the same host and port, so code changes are picked up without hunting for the old window.

`run_start` calls `replace_running_advisor(host, port) -> str | None` before building the database and before opening the browser. It returns `None` when the port is free and an error message when it is not:

1. If nothing is listening on the port (`port_in_use(host, port)` is false), start normally.
2. Otherwise ask `GET http://<host>:<port>/api/health` (`running_advisor_pid(host, port)`, 2 s timeout). If the reply is JSON with `app == "btd6"` and an int `pid`, that is our advisor: print `Stopping the advisor that is already running (pid N)...`, call `stop_process(pid)` (`os.kill(pid, signal.SIGTERM)`; on Windows this terminates the process), and wait up to `STOP_TIMEOUT_SECONDS` (10) for the port to free (`wait_for_port_free`). If it frees, start normally. If not, return `Could not stop the advisor on port P (pid N). Close its window and run the start script again.`
3. If the port is in use and there is no advisor health reply (another program, or an advisor from before `/api/health` existed), return `Port P is already in use. If an older BTD6 advisor is running, close its window (or press Ctrl+C in it) and run the start script again; otherwise use --port N.`

When an error message is returned, `start` prints it to stderr and exits with code 1 without opening the browser or launching the game.

`stop_process` never targets the current process (`pid == os.getpid()` is ignored), and a `ProcessLookupError` (already exited) counts as stopped.
