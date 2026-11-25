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

### `GET /api/recommendations`: `one_per_tower` and `owned` (repeated)

`RecommendOptions` gains `one_per_tower: bool = False` and `owned: tuple[OwnedTower, ...] = ()`. `form_to_recommend_options` accepts `owned` as a `str`, a list of `str` or `None`; the endpoint reads every `owned` value from the query string (`request.query_params.getlist`). `one_per_tower` accepts `true`/`false`/`1`/`0`/`on` (case-insensitive), blank or absent is false. Rows carry `upgrade_from` after `total_cost`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`one_per_tower`|A) Value|A1: Absent or blank|none, `""`, `"  "`|
|||A2: True spelling|`true`, `TRUE`, `1`, `on`|
|||A3: False spelling|`false`, `0`|
|||A4: Other|`yes`, `2`, `maybe`|
|`owned`|B) Values|B1: Absent|none|
|||B2: One valid|`Super Monkey 0-0-0`|
|||B3: Repeated valid|`Super Monkey 0-0-0`, `Super Monkey 1-0-0`|
|||B4: Tower not in the database|`Banana Farm 2-0-0`|
|||B5: Not `<name> X-Y-Z`|`Ninja`, `Ninja Monkey 1-2`|
|||B6: Valid then invalid|`Super Monkey 0-0-0`, `Ninja`|
|||B7: Path digit above 5|`Super Monkey 6-0-0`|

Base case: A1, B1

### Base Choice Coverage

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | 200, rows have `upgrade_from` `null`, key order `tower_name, path, total_cost, upgrade_from` | `test_recommendations_include_upgrade_from_field` |
| T2 | A2 | B1 | 200, one row | `test_recommendations_one_per_tower[true]`, `[1]` |
| T3 | A3 | B1 | 200, four rows | `test_recommendations_one_per_tower[false]` |
| T4 | A4 | B1 | 422 `one_per_tower must be true or false, got 'yes'` | `test_recommendations_new_params_invalid_is_422[one_per_tower]` |
| T5 | A1 | B2 | 200, rows equal `recommend(..., owned=[...])`, `3-0-0` upgrade costs 24500 | `test_recommendations_owned_single` |
| T6 | A1 | B3 | rows equal `recommend` with both entries; `3-0-0` has `upgrade_from` `None`, `0-0-0`, `1-0-0` | `test_recommendations_owned_repeated` |
| T7 | A1 | B4 | rows equal the default | `test_recommendations_owned_unknown_tower_is_ignored` |
| T8 | A1 | B5 | 422 `owned must be '<tower name> X-Y-Z', got 'Ninja'` | `test_recommendations_new_params_invalid_is_422[owned]`, `[short_path]` |
| T9 | A1 | B6 | 422 on the invalid value | `test_recommendations_new_params_invalid_is_422[second_owned]` |
| T10 | A1 | B7 | 422 | `test_recommendations_owned_path_digit_out_of_range_is_422` |

`form_to_recommend_options` rows (`tests/test_api_params_recommend.py`): `test_recommend_options_one_per_tower_*`, `test_recommend_options_owned_*` (str, one-item list, two items, multi-word name, empty list, `None`, no trailing path).

Frontend static checks (`tests/test_frontend_recommend.py`): `recommend-one-per-tower` checkbox (`name="one_per_tower"`, `value="true"`, unchecked, inside `recommend-form`), the `Upgrade from` column after `Path` in `RECOMMEND_COLUMNS`, `append("owned"` and `Counting ` ... `owned towers` in `app.js`.

## `GET /api/health`

```python
def health() -> dict[str, object]
```
Returns the app name and server process id so `start` can find and replace a running advisor. No database access.

### ISP

| Parameter | Characteristic | Partition | Value |
|---|---|---|---|
| database file | A) State | A1: Exists | fixture database |
| | | A2: Missing | `tmp_path / "missing.db"` |

Base case: A1

### Base Choice Coverage

| BCC Test | A | Oracle | Test Name |
|---|---|---|---|
| T1 | A1 | 200, `{"app": "btd6", "pid": os.getpid()}` | `test_health_reports_app_and_pid` |
| T2 | A2 | same body (no 503) | `test_health_works_without_database` |
