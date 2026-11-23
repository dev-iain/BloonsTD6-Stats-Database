# `create_app(database_path)` in `btd6/api/app.py`

Endpoints are tested with `TestClient` against a database file copied from an in-memory `build_database` (each request opens its own connection, so `:memory:` cannot be shared). See `docs/web.md` for the contract.

| Situation | Status | Body |
|---|---|---|
| `/api/upgrades`, no params | 200 | every row |
| numeric minimum (`min_pierce=6`) | 200 | only rows at or above it |
| `sort=projectile_pierce&limit=2` | 200 | top two, descending |
| `damage_type=Plasma` | 200 | only that type |
| unknown `sort` | 422 | `error` starts `Cannot sort by` |
| negative `min_damage` | 422 | `error` names `min_damage` |
| invalid pop choice (`lead=maybe`) | 422 | `error` set |
| `/api/rankings` default | 200 | rows with `tower_name`, `path`, `total_cost`, `dps`, `damage_per_dollar` |
| `metric=dps` | 200 | sorted by `dps` descending |
| unknown `metric` | 422 | `error` starts `Cannot rank by` |
| unknown `difficulty` | 422 | `error` set |
| `/api/damage-types` | 200 | seeded names |
| database file missing | 503 | `error` mentions `python -m btd6 load` |
| `/` and `/static/*` | 200 | frontend files |
