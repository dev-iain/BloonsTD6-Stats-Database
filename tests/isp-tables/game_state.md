# Live game state: `btd6/game_state.py` and the `fake-state` / `game-state` commands

## Rules for these tests

- The contract is `docs/game-state.md`. Invalid payloads raise `GameStateError` (a `ValueError`); a missing file raises `NoGameStateError` and an old one `StaleGameStateError`, both subclasses of `GameStateError`.
- `VALID` is `tests/fixtures/game_state/valid.json`: version 1, round 40, cash 5123.7, lives 150, difficulty `Medium`, mode `Standard`, map `Monkey Meadow`, towers `DartMonkey [0,2,3]` and `BananaFarm [2,0,0]`. Cases below change one key of `VALID`.
- `NOW` is `datetime(2026, 11, 24, 12, 0, 30, tzinfo=UTC)`; saved states use `received_at = datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)` (age 30 s).
- Files go in `tmp_path`; nothing reads the real `game_state.json`.

---

## parse_game_state

```python
def parse_game_state(payload: Mapping[str, object]) -> GameState
```
Validates a mod payload and returns a `GameState` with normalised `round_number`, `money`, `lives`, `difficulty`, `mode`, `map_name` and `towers` (`PlacedTower(base_id, tower_name, path, known)`).

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`payload["version"]`|A) Version|A1: Supported|`1`|
|||A2: Unsupported|`2`|
|||A3: Missing|key removed|
|`payload["round"]`|B) Round|B1: Above 1|`40`|
|||B2: Lowest valid|`1`|
|||B3: Below 1|`0`|
|||B4: Not an int|`"40"`|
|||B5: Boolean|`True`|
|`payload["cash"]`|C) Cash|C1: Fractional positive|`5123.7`|
|||C2: Zero|`0`|
|||C3: Negative|`-1`|
|||C4: Not a number|`"5000"`|
|`payload["difficulty"]` and `payload["mode"]`|D) Difficulty with mode|D1: Medium, Standard|`"Medium"`, `"Standard"`|
|||D2: Hard, Impoppable|`"Hard"`, `"Impoppable"`|
|||D3: Hard, CHIMPS|`"Hard"`, `"CHIMPS"`|
|||D4: Unknown difficulty|`"Nightmare"`, `"Standard"`|
|`payload["towers"]`|E) Towers|E1: Known and unknown towers|`VALID` towers|
|||E2: Empty|`[]`|
|||E3: Tier out of range|`[{"base_id": "DartMonkey", "tiers": [0, 6, 0]}]`|
|||E4: Wrong tier count|`[{"base_id": "DartMonkey", "tiers": [0, 2]}]`|
|||E5: Not a list|`"DartMonkey"`|

Base case: A1, B1, C1, D1, E1

### Base Choice Coverage

| BCC Test | A | B | C | D | E | Oracle | Test Name |
|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | `round_number == 40`, `money == 5123`, `lives == 150`, `difficulty == "medium"`, `mode == "Standard"`, `map_name == "Monkey Meadow"`, towers `(PlacedTower("DartMonkey", "Dart Monkey", "0-2-3", True), PlacedTower("BananaFarm", None, "2-0-0", False))` | `test_parse_game_state_all_base` |
| T2 | A2 | B1 | C1 | D1 | E1 | raises `GameStateError` | `test_parse_game_state_unsupported_version` |
| T3 | A3 | B1 | C1 | D1 | E1 | raises `GameStateError` | `test_parse_game_state_missing_version` |
| T4 | A1 | B2 | C1 | D1 | E1 | `round_number == 1` | `test_parse_game_state_round_one` |
| T5 | A1 | B3 | C1 | D1 | E1 | raises `GameStateError` | `test_parse_game_state_round_zero` |
| T6 | A1 | B4 | C1 | D1 | E1 | raises `GameStateError` | `test_parse_game_state_round_not_int` |
| T7 | A1 | B5 | C1 | D1 | E1 | raises `GameStateError` | `test_parse_game_state_round_boolean` |
| T8 | A1 | B1 | C2 | D1 | E1 | `money == 0` | `test_parse_game_state_zero_cash` |
| T9 | A1 | B1 | C3 | D1 | E1 | raises `GameStateError` | `test_parse_game_state_negative_cash` |
| T10 | A1 | B1 | C4 | D1 | E1 | raises `GameStateError` | `test_parse_game_state_cash_not_number` |
| T11 | A1 | B1 | C1 | D2 | E1 | `difficulty == "impoppable"` | `test_parse_game_state_impoppable` |
| T12 | A1 | B1 | C1 | D3 | E1 | `difficulty == "hard"` | `test_parse_game_state_chimps` |
| T13 | A1 | B1 | C1 | D4 | E1 | raises `GameStateError` | `test_parse_game_state_unknown_difficulty` |
| T14 | A1 | B1 | C1 | D1 | E2 | `towers == ()` | `test_parse_game_state_no_towers` |
| T15 | A1 | B1 | C1 | D1 | E3 | raises `GameStateError` | `test_parse_game_state_tier_out_of_range` |
| T16 | A1 | B1 | C1 | D1 | E4 | raises `GameStateError` | `test_parse_game_state_wrong_tier_count` |
| T17 | A1 | B1 | C1 | D1 | E5 | raises `GameStateError` | `test_parse_game_state_towers_not_list` |

---

## tower_name_from_game_id

```python
def tower_name_from_game_id(base_id: str) -> str | None
```
Maps a game id to the database tower name for every name in `KNOWN_TOWERS` (spaces removed); otherwise `None`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`base_id`|A) Kind of id|A1: Known two-word tower|`"DartMonkey"`|
|||A2: Known one-word tower|`"Druid"`|
|||A3: Unknown tower|`"BananaFarm"`|
|||A4: Database name with space|`"Dart Monkey"`|

Base case: A1

### Base Choice Coverage

| BCC Test | A | Oracle | Test Name |
|---|---|---|---|
| T1 | A1 | `"Dart Monkey"` | `test_tower_name_from_game_id_two_words` |
| T2 | A2 | `"Druid"` | `test_tower_name_from_game_id_one_word` |
| T3 | A3 | `None` | `test_tower_name_from_game_id_unknown` |
| T4 | A4 | `None` | `test_tower_name_from_game_id_database_name` |

---

## save_game_state / load_game_state

```python
def save_game_state(path: Path, state: GameState, received_at: datetime) -> None
def load_game_state(path: Path, max_age_seconds: float | None = DEFAULT_MAX_AGE_SECONDS, now: datetime | None = None) -> StoredGameState
```
`save_game_state` writes `state_to_payload(state)` plus `received_at` atomically; `load_game_state` reads it back as `StoredGameState(state, received_at)` and checks staleness against `now` (default: current UTC time).

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`path` (state)|A) File|A1: Saved state|`save_game_state(path, parse_game_state(VALID), received_at)`|
|||A2: Missing|nothing written|
|||A3: Not valid JSON|`"{not json"`|
|`max_age_seconds` vs age|B) Age relative to limit|B1: Under the limit|`60`|
|||B2: Equal to the limit|`30`|
|||B3: Over the limit|`29`|
|||B4: Check disabled|`None`|

Base case: A1, B1

### Base Choice Coverage

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | `stored.state == parse_game_state(VALID)`, `stored.received_at == received_at` | `test_load_game_state_all_base` |
| T2 | A2 | B1 | raises `NoGameStateError` | `test_load_game_state_missing_file` |
| T3 | A3 | B1 | raises `GameStateError` | `test_load_game_state_invalid_json` |
| T4 | A1 | B2 | returns the state | `test_load_game_state_age_equal_to_limit` |
| T5 | A1 | B3 | raises `StaleGameStateError` | `test_load_game_state_stale` |
| T6 | A1 | B4 | returns the state | `test_load_game_state_no_age_check` |

Property (hypothesis): for any valid payload, `parse_game_state(state_to_payload(parse_game_state(payload)))` equals `parse_game_state(payload)` (`test_state_to_payload_round_trip`).

---

## main: `fake-state` and `game-state`

```python
def main(argv: list[str] | None = None) -> int
```
`--state-file PATH` is global (default `game_state.json` in the project root). `fake-state --round N --money X [--difficulty D] [--tower "NAME:X-Y-Z" ...]` saves a state built by `fake_game_state` with `received_at` = now and prints `Saved round N, $X to PATH`. `game-state [--max-age S]` prints the stored state; `--max-age 0` means no check.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|command|A) Command and file state|A1: `fake-state` then `game-state`|`fake-state --round 40 --money 5000 --tower "Dart Monkey:0-2-3"`, then `game-state`|
|||A2: `game-state` with no file|`game-state`|
|||A3: `game-state` with a stale file|saved 60 s ago, `game-state --max-age 30`|
|`--tower`|B) Tower spec|B1: Valid known tower|`"Dart Monkey:0-2-3"`|
|||B2: Malformed spec|`"Dart Monkey"`|
|||B3: Unknown tower name|`"Banana Farm:2-0-0"`|

Base case: A1, B1

### Base Choice Coverage

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | both exit 0; `game-state` stdout contains `Round 40`, `Money $5,000`, `Difficulty medium` and `Dart Monkey 0-2-3` | `test_main_fake_state_then_game_state` |
| T2 | A2 | B1 | exit 1, stderr `No game state at <path>. Start the game with the mod and "python -m btd6 serve", or run "python -m btd6 fake-state".` | `test_main_game_state_missing` |
| T3 | A3 | B1 | exit 1, stderr starts with `Game state is stale` | `test_main_game_state_stale` |
| T4 | A1 | B2 | exit 2, stderr `Tower must be NAME:X-Y-Z, got "Dart Monkey"` | `test_main_fake_state_malformed_tower` |
| T5 | A1 | B3 | exit 2, stderr `Unknown tower "Banana Farm"` | `test_main_fake_state_unknown_tower` |

### Mutation gaps

Tests in `tests/test_game_state_mutation_gaps.py`. Equivalent mutants skipped: `allow_empty=None`, temp suffix, encoding spelling, `"HARD".capitalize()`.

|Test Name|Kills|
|---|---|
|`test_missing_key_message`|exact `Missing key: round` text|
|`test_integer_below_minimum_message`|exact integer-minimum text|
|`test_negative_cash_message`|exact negative cash text|
|`test_non_string_text_message`|exact non-string text message|
|`test_tower_not_object_message`|exact tower-not-object text|
|`test_bad_tiers_message`|exact bad tiers text|
|`test_towers_not_list_message`|exact towers-not-list text|
|`test_unsupported_version_message`|exact version text|
|`test_unknown_difficulty_message_from_parse`|exact difficulty text in `parse_game_state`|
|`test_unknown_difficulty_message_from_fake`|exact difficulty text in `fake_game_state`|
|`test_invalid_received_at_message`|exact `received_at` text|
|`test_invalid_json_file_message`|exact invalid JSON text|
|`test_non_object_json_file_message`|exact non-object file text|
|`test_stale_message_is_exact`|exact stale text, `:.0f` and `:g` formats|
|`test_bad_fake_tower_path_message`|exact fake tower path text|
|`test_empty_base_id_raises`|`allow_empty=False` for `base_id`|
|`test_empty_required_text_raises`|empty `difficulty`/`mode` accepted|
|`test_non_string_map_raises`|map type check|
|`test_empty_map_allowed`|`allow_empty=True` for map|
|`test_game_id_from_name_strips_spaces`|replace argument mutations|
|`test_tower_ids_maps_back_to_name`|`TOWER_IDS` key/value swap|
|`test_parse_tower_spec_splits_on_first_colon`|partition vs rpartition/split|
|`test_naive_received_at_is_utc`|UTC fallback for naive timestamps|
|`test_aware_received_at_keeps_offset`|aware timestamps not overwritten|
|`test_save_leaves_only_target_file`|temp file left behind / wrong dir|
|`test_fake_tower_fields`|`tower_name` and `known` values|
|`test_fake_game_state_mode`|mode strings and `map_name`|
