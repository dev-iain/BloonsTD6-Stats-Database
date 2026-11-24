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
| `GET /api/rounds/{n}` | none | `{"round", "summary", "composition", "groups", "income"}`: `summary` is `RoundSummary` (totals plus `has_moab`/`has_camo`/`has_lead`/`has_ceramic`), `composition` the bloon totals (groups merged by bloon and modifiers, with `count` and `total_rbe`, largest RBE first), `groups` the spawn order, `income` is `pop_cash`, `end_bonus`, `total`, `cumulative` or `null` when income data is not loaded |

Parameters are parsed by `btd6.api.params.form_to_filters` and `form_to_search_options`. Each request opens its own SQLite connection.

## Layout

- `btd6/api/app.py`: `create_app(database_path)`, routes, error handlers, static mount.
- `frontend/`: `index.html`, `style.css`, `app.js` (ES module, no dependencies). Served at `/` and `/static/`. Table cells are set with `textContent`, never `innerHTML`.
- Search, Rankings and Rounds tabs are live. The Rounds tab shows Summary and Income cards (money in green), then a bloon totals table and the spawn order table.
