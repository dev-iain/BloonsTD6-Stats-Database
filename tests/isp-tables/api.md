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
| rankings `money=5000` | 200 | only rows with `total_cost` at most 5000 |
| rankings `money` blank | 200 | every row (no cap) |
| rankings `money=-1` or `money=lots` | 422 | `error` names `money` |
| rankings `tower=Super Monkey` | 200 | only that tower's rows |
| rankings `tower=Dart Monkey` (not loaded) | 200 | no rows |
| `/api/towers` | 200 | `towers` is the loaded tower names, sorted |
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

---

## `GET /api/agent`

```python
def agent(request: Request) -> dict[str, Any]
```
Runs the advisor agent once and returns `{"answer", "picks", "tool_calls"}` (tool results omitted). Order: validate params (422), build client (503 missing key), load live state (404/422), run (502 `AgentError`, 503 missing db).

### ISP

| Parameter | Characteristic | Partition | Value |
|---|---|---|---|
| `round`, `money` | A) Validity | A1: Valid | `63`, `5000` |
| | | A2: Invalid or missing | `money=lots`, `-1`, omitted round |
| `max_iterations` | B) Value | B1: Omitted (8) | none |
| | | B2: Not an integer | `many` |
| client factory | C) Outcome | C1: Answers | scripted tool call then answer |
| | | C2: Raises `MissingApiKeyError` | factory raises |
| | | C3: `AgentError` | iteration cap 1, or provider error |
| `live` | D) Live | D1: Absent or not `true` | none, `false` |
| | | D2: `true`, fresh state | saved with owned Super Monkey |
| | | D3: `true`, no state | none |
| | | D4: `true`, stale state | clock +60 s |
| database | E) State | E1: Exists | fixture |
| | | E2: Missing | `missing.db` |

Base case: A1, B1, C1, D1, E1

### Base Choice Coverage

| BCC Test | A | B | C | D | E | Oracle | Test Name |
|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | 200 body with answer, parsed picks, tool call names and arguments | `test_agent_all_base` |
| T2 | A2 | B1 | C1 | D1 | E1 | 422 `{"error"}`, client never called | `test_agent_invalid_params_are_422` |
| T3 | A1 | B2 | C1 | D1 | E1 | 422 | `test_agent_invalid_params_are_422[iterations_text]` |
| T4 | A1 | B1 | C2 | D1 | E1 | 503 with the message | `test_agent_missing_key_is_503` |
| T5 | A1 | B1 | C3 | D1 | E1 | 502 with the message | `test_agent_error_is_502`, `test_agent_provider_error_is_502` |
| T6 | A1 | B1 | C1 | D2 | E1 | 200; user message names the owned tower | `test_agent_live_passes_owned_towers` |
| T7 | A1 | B1 | C1 | D3 | E1 | 404 | `test_agent_live_without_state_is_404` |
| T8 | A1 | B1 | C1 | D4 | E1 | 422 stale | `test_agent_live_stale_state_is_422` |
| T9 | A1 | B1 | C1 | D1 | E2 | 503 | `test_agent_missing_database_is_503` |

## `POST /api/shutdown` (Quit)

`create_app(..., request_stop=None)`; the default is `btd6.api.app.stop_server`, which raises `SIGINT` so uvicorn exits gracefully. Tests inject a spy and never call the default. The stop runs as a background task, after the response.

### ISP

| Parameter | Characteristic | Block | Value |
|---|---|---|---|
| request | A) Method | A1: POST | `POST /api/shutdown` |
| | | A2: GET | `GET /api/shutdown` |
| request | B) `X-BTD6-Action` header | B1: `quit` | `quit` |
| | | B2: absent | none |
| | | B3: other value | `stop` |

Base case: A1, B1. Only meaningful combinations (A2 ignores B).

### Base Choice Coverage

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | 200 `{"stopping": true}`, spy called once | `test_shutdown_with_header_stops_once` |
| T2 | A1 | B2 | 403 `{"error": "Missing X-BTD6-Action: quit header"}`, spy not called | `test_shutdown_without_header_is_forbidden` |
| T3 | A1 | B3 | 403 same body, spy not called | `test_shutdown_wrong_header_is_forbidden` |
| T4 | A2 | B1 | 405, spy not called | `test_shutdown_get_is_not_allowed` |

`stop_server` raises `signal.SIGINT` exactly once (`test_stop_server_raises_sigint`). Default wiring: `test_create_app_default_stop_is_stop_server`.

## Auto-stop when the tab closes (`btd6/api/presence.py`)

`PagePresence(token, idle_seconds=90, grace_seconds=5)` is pure and clock-driven (`heartbeat`, `closing`, `live_pages`, `should_stop`). `should_stop` is false until a page has ever connected, false while any page is live, otherwise true once empty for `grace_seconds` (empty since = later of the last emptying `closing` and last heartbeat + idle). `watch_presence` polls and calls `request_stop` once. `create_app(presence=None, auto_stop=False)`; `app.state.auto_stop`; `start` enables it unless `--no-browser`, `serve` never.

### ISP (`should_stop`)

| Characteristic | Blocks |
|---|---|
| A) History | A1: never connected; A2: page live; A3: page closed; A4: page crashed (no closing) |
| B) Time since empty | B1: under grace; B2: exactly grace; B3: over grace |
| C) Pages | C1: one; C2: two, one closes; C3: two, both close |
| D) Later heartbeat | D1: none; D2: reload within grace; D3: after stop |

Base case: A3, B2, C1, D1. Tests in `tests/test_presence.py` (never connected, 4.9 s vs 5 s, reload, two pages, 90/94/95 s crash, revive).

### `POST /api/presence` and `GET /api/session`

| Characteristic | Blocks |
|---|---|
| E) Token | E1: right; E2: wrong; E3: missing |
| F) Body | F1: valid object; F2: bad JSON; F3: non-object; F4: page missing/blank; F5: unknown event |
| G) Content type | G1: `application/json`; G2: `text/plain` (sendBeacon) |
| H) Event | H1: heartbeat; H2: closing |

Base case: E1, F1, G1, H1 -> 204, presence called with page and `clock()`. E2/E3 -> 403 `{"error": "Bad session token"}`, presence unchanged. F2-F5 -> 422 `{"error"}`. `GET /api/session` -> `{"token", "auto_stop", "heartbeat_seconds": 10}`; default token is `secrets.token_urlsafe(16)`, stable. Watchdog runs only with `auto_stop=True` (`test_auto_stop_off_never_stops`, `test_auto_stop_on_stops_when_empty`). CLI: `tests/test_cli_auto_stop.py`.
