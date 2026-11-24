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
| `/api/rounds/10` | 200 | `round`, `summary` flags, ordered `groups`, `income` |
| `/api/rounds/10`, no income data | 200 | `income` is `null` |
| round 0, -3 or past the last loaded | 422 | `error` set |
| round not an integer | 422 | validation error |
| `/api/rounds/1`, no round data | 404 | `error` starts `No round data` |
| `/api/rounds` | 200 | `first`/`last` loaded rounds, `null` when empty |
| database file missing | 503 | `error` mentions `python -m btd6 load` |
| `/` and `/static/*` | 200 | frontend files |

## `GET /api/recommendations` (#123)

Query parameters `round` (required int), `money` (required int), `difficulty` (default `medium`), `limit` (blank or absent means none). Parsed by `btd6.api.params.form_to_recommend_options(form) -> RecommendOptions` (frozen dataclass `round_number`, `money`, `difficulty`, `limit`), then passed to `recommend`. Response `{"rows": [...]}`: each row is `asdict(Recommendation)` with `reasons` as a JSON list, in `recommend` order. Fixture: `tests/recommend_fixture.py` saved to a file.

| Situation | Status | Body |
|---|---|---|
| `round=63&money=100000` | 200 | rows equal `recommend(conn, 63, 100000)` (paths `3-0-0`, `0-0-4`; `reasons` lists) |
| `round=40&money=100000&limit=1` | 200 | one row, `0-0-0` |
| `round=63&money=100000&difficulty=hard` | 200 | `3-0-0` `total_cost` `29160` |
| `round=1&money=100` | 200 | `rows` is `[]` |
| `money=-1` | 422 | `error` `money must be 0 or more, got -1` |
| `money=abc` | 422 | `error` `money must be a whole number, got 'abc'` |
| `money` absent | 422 | `error` `money is required` |
| `round` absent | 422 | `error` `round is required` |
| `round=abc` | 422 | `error` `round must be a whole number, got 'abc'` |
| `difficulty=nightmare` | 422 | `error` set |
| `limit=0` | 422 | `error` `limit must be at least 1, got 0` |
| `round=150` (not loaded) | 422 | `error` `Round 150 is not loaded; loaded rounds are 1-101` |
| no round data loaded | 404 | `error` starts `No round data` |
| database file missing | 503 | `error` mentions `python -m btd6 load` |

Tests: `tests/test_api_recommendations.py`; `form_to_recommend_options` rows go in `tests/test_api_params_recommend.py` (required/absent, blank, whitespace-padded `" 63 "` accepted, non-integer, `"1.5"` rejected as not a whole number, negative money rejected, `limit` blank → `None`, `difficulty` default `"medium"`).
