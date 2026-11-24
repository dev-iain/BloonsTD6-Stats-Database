# Live game state over HTTP: `state_summary`, `POST/GET /api/game-state` and the live toggle

## Rules for these tests

- The contract is `docs/game-state.md`. `VALID` is `tests/fixtures/game_state/valid.json` (round 40, cash 5123.7, `Medium`/`Standard`, towers `DartMonkey [0,2,3]` and `BananaFarm [2,0,0]`).
- `RECEIVED_AT` is `datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)`.
- The app is built with `create_app(database_path, state_path=tmp_path / "game_state.json", clock=lambda: now)`, so tests never touch the real `game_state.json` or the real clock.

---

## state_summary

```python
def state_summary(stored: StoredGameState, now: datetime, max_age_seconds: float | None = DEFAULT_MAX_AGE_SECONDS) -> dict[str, object]
```
Returns the JSON view of a stored state: `round`, `money`, `lives`, `difficulty` (recommender value), `mode`, `map`, `towers` (`base_id`, `tower_name`, `path`, `known`), `received_at`, `age_seconds` and `stale`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`now` and `max_age_seconds`|A) Age against the limit|A1: Within the limit|`now` = `RECEIVED_AT + 10 s`, limit `30`|
|||A2: Exactly at the limit|`now` = `RECEIVED_AT + 30 s`, limit `30`|
|||A3: Over the limit|`now` = `RECEIVED_AT + 31 s`, limit `30`|
|||A4: No limit|`now` = `RECEIVED_AT + 3600 s`, limit `None`|
|`stored.state`|B) Mode|B1: Standard|`VALID`|
|||B2: Impoppable|`VALID` with `difficulty` `"Hard"`, `mode` `"Impoppable"`|
|`stored.state.towers`|C) Towers|C1: Known and unknown|`VALID` towers|
|||C2: None|`[]`|

Base case: A1, B1, C1

### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | `{"round": 40, "money": 5123, "lives": 150, "difficulty": "medium", "mode": "Standard", "map": "Monkey Meadow", "towers": [{"base_id": "DartMonkey", "tower_name": "Dart Monkey", "path": "0-2-3", "known": True}, {"base_id": "BananaFarm", "tower_name": None, "path": "2-0-0", "known": False}], "received_at": "2026-11-24T12:00:00+00:00", "age_seconds": 10.0, "stale": False}` | `test_state_summary_all_base` |
| T2 | A2 | B1 | C1 | `age_seconds == 30.0`, `stale is False` | `test_state_summary_at_limit` |
| T3 | A3 | B1 | C1 | `age_seconds == 31.0`, `stale is True` | `test_state_summary_over_limit` |
| T4 | A4 | B1 | C1 | `age_seconds == 3600.0`, `stale is False` | `test_state_summary_no_limit` |
| T5 | A1 | B2 | C1 | `difficulty == "impoppable"`, `mode == "Impoppable"` | `test_state_summary_impoppable` |
| T6 | A1 | B1 | C2 | `towers == []` | `test_state_summary_no_towers` |

---

## POST /api/game-state

```
POST /api/game-state  (JSON body: a version 1 payload)
```
Validates the body with `parse_game_state`, saves it with `received_at = clock()` and returns its `state_summary`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|request body|A) Body|A1: Valid payload|`VALID`|
|||A2: Invalid payload|`VALID` with `round` `0`|
|||A3: JSON but not an object|`[1, 2]`|
|||A4: Not JSON|`"not json"` as raw bytes|
|state file before the call|B) Existing file|B1: None|no file|
|||B2: Older state|a saved state for round 12|

Base case: A1, B1

### Base Choice Coverage

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | 200; body `round == 40`, `money == 5123`, `age_seconds == 0.0`, `stale is False`; file holds round 40 and `received_at` `"2026-11-24T12:00:00+00:00"` | `test_post_game_state_all_base` |
| T2 | A2 | B1 | 422; `error` is `"round must be an integer >= 1"`; no file written | `test_post_game_state_invalid_payload` |
| T3 | A3 | B1 | 422; `error` is `"Game state must be a JSON object"`; no file written | `test_post_game_state_not_object` |
| T4 | A4 | B1 | 422; `error` is `"Game state must be a JSON object"`; no file written | `test_post_game_state_not_json` |
| T5 | A1 | B2 | 200; file now holds round 40 | `test_post_game_state_replaces_older_state` |

---

## GET /api/game-state

```
GET /api/game-state
```
Returns the stored state's `state_summary` at `clock()` with the default 30 s limit; a stale state is still returned, with `stale: true`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|state file|A) File|A1: Fresh state|saved at `RECEIVED_AT`, `now` = `RECEIVED_AT + 5 s`|
|||A2: Stale state|saved at `RECEIVED_AT`, `now` = `RECEIVED_AT + 60 s`|
|||A3: Missing|no file|
|||A4: Corrupt|file text `"{"`|

Base case: A1

### Base Choice Coverage

| BCC Test | A | Oracle | Test Name |
|---|---|---|---|
| T1 | A1 | 200; `round == 40`, `age_seconds == 5.0`, `stale is False`, towers as in `state_summary` T1 | `test_get_game_state_all_base` |
| T2 | A2 | 200; `age_seconds == 60.0`, `stale is True` | `test_get_game_state_stale` |
| T3 | A3 | 404; `error` starts with `"No game state at"` | `test_get_game_state_missing` |
| T4 | A4 | 422; `error` contains `"is not valid JSON"` | `test_get_game_state_corrupt` |

Not BCC: `test_post_then_get_round_trip` posts `VALID` and checks the GET returns the same summary.

---

## Recommend tab live toggle (`frontend/index.html`, `frontend/app.js`)

Static checks on the page and script, in the style of `tests/test_frontend_recommend.py`.

| Check | Oracle | Test Name |
|---|---|---|
| Live checkbox exists | `id="recommend-live"` with `type="checkbox"` in the page | `test_index_has_live_toggle` |
| Live status line exists | `id="recommend-live-status"` in the page | `test_index_has_live_status` |
| Script polls the endpoint | `"/api/game-state"` in `app.js` | `test_app_polls_game_state_endpoint` |
| Poll interval | `LIVE_POLL_MS = 2000` in `app.js` | `test_app_polls_every_two_seconds` |
| Missing game message | `"No game connected"` in `app.js` | `test_app_shows_no_game_message` |
| Stale game message | `"Game state is stale"` in `app.js` | `test_app_shows_stale_message` |
| Live status format | `"Live · round "` and `"s ago"` in `app.js` | `test_app_shows_live_status` |
