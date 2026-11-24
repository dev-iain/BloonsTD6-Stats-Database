# Live game state in the CLI and the agent: `--live`, `get_game_state`, `run_agent(state_path=...)`

## Rules for these tests

- States are written with `save_game_state(path, fake_game_state(...), received_at)` into `tmp_path`. "Fresh" means `received_at = datetime.now(UTC)`; "stale" means `received_at` one hour ago.
- `LIVE_STATE` is `fake_game_state(63, 100000, "medium", [("Super Monkey", "2-0-0")])`.
- The database is `tests/recommend_fixture.build_recommend_database()`; the LLM is `ScriptedClient` or a stub, never the network.

---

## main: `recommend --live` / `agent --live`

```
python -m btd6 [--state-file PATH] recommend --live [--max-age S] [--limit N]
python -m btd6 [--state-file PATH] agent --live [--max-age S] [--max-iterations K]
```
Reads round, money and difficulty from the stored game state instead of `--round`, `--money` and `--difficulty`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|options|A) Source of round and money|A1: `--live` alone|`--live`|
|||A2: `--round`/`--money` alone|`--round 63 --money 100000`|
|||A3: `--live` with `--round`|`--live --round 5`|
|||A4: Neither|no options|
|state file|B) Stored state|B1: Fresh|`LIVE_STATE`, fresh|
|||B2: Stale|`LIVE_STATE`, stale|
|||B3: Missing|no file|
|`--max-age`|C) Age limit|C1: Default (30 s)|not given|
|||C2: Off|`--max-age 0`|
|state difficulty|D) Difficulty|D1: medium|`LIVE_STATE`|
|||D2: hard|`LIVE_STATE` with difficulty `"hard"`|

Base case: A1, B1, C1, D1

### Base Choice Coverage (`recommend`)

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | exit 0; first line `Live game: round 63, $100,000, difficulty medium`; the rest equals the output of `recommend --round 63 --money 100000` | `test_main_recommend_live_all_base` |
| T2 | A2 | B1 | C1 | D1 | exit 0; output has no `Live game:` line | `test_main_recommend_live_not_used` |
| T3 | A3 | B1 | C1 | D1 | `SystemExit(2)`; stderr ends with `--live cannot be combined with --round, --money or --difficulty` | `test_main_recommend_live_with_round` |
| T4 | A4 | B1 | C1 | D1 | `SystemExit(2)`; stderr names `--round` and `--money` | `test_main_recommend_live_neither` |
| T5 | A1 | B2 | C1 | D1 | exit 1; stderr starts with `Game state is stale` | `test_main_recommend_live_stale` |
| T6 | A1 | B3 | C1 | D1 | exit 1; stderr starts with `No game state at` | `test_main_recommend_live_missing` |
| T7 | A1 | B2 | C2 | D1 | exit 0; first line `Live game: round 63, $100,000, difficulty medium` | `test_main_recommend_live_max_age_off` |
| T8 | A1 | B1 | C1 | D2 | exit 0; first line ends `difficulty hard`; rest equals `recommend --round 63 --money 100000 --difficulty hard` | `test_main_recommend_live_hard` |

### Base Choice Coverage (`agent`)

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | exit 0; the first user message is `Round 63, money $100000, difficulty medium. You own: Super Monkey 2-0-0. Recommend what to buy.`; the tools sent include `get_game_state` | `test_main_agent_live_all_base` |
| T2 | A2 | B1 | exit 0; the tools sent do not include `get_game_state` | `test_main_agent_live_not_used` |
| T3 | A3 | B1 | `SystemExit(2)` | `test_main_agent_live_with_round` |
| T4 | A1 | B3 | exit 1; stderr starts with `No game state at`; the client is never called | `test_main_agent_live_missing` |

---

## call_tool(..., "get_game_state", ...)

```python
def call_tool(connection, name, arguments, state_path: Path | None = None) -> dict
```
`get_game_state` returns `state_summary` of the stored state, or a structured error.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`state_path`|A) Live run|A1: Path given|`tmp_path / "game_state.json"`|
|||A2: Not live|`None`|
|state file|B) Stored state|B1: Fresh|`LIVE_STATE`, fresh|
|||B2: Stale|`LIVE_STATE`, stale|
|||B3: Missing|no file|
|`arguments`|C) Arguments|C1: Empty|`{}`|
|||C2: Unexpected key|`{"round": 1}`|

Base case: A1, B1, C1

### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | `round == 63`, `money == 100000`, `difficulty == "medium"`, `towers == [{"base_id": "SuperMonkey", "tower_name": "Super Monkey", "path": "2-0-0", "known": True}]`, `stale is False` | `test_call_tool_get_game_state_all_base` |
| T2 | A2 | B1 | C1 | `{"error": {"type": "LiveStateUnavailable", ...}}` | `test_call_tool_get_game_state_not_live` |
| T3 | A1 | B2 | C1 | error type `StaleGameStateError` | `test_call_tool_get_game_state_stale` |
| T4 | A1 | B3 | C1 | error type `NoGameStateError` | `test_call_tool_get_game_state_missing` |
| T5 | A1 | B1 | C2 | error type `TypeError` | `test_call_tool_get_game_state_unexpected_argument` |

Also: `LIVE_TOOL_SCHEMAS` is `TOOL_SCHEMAS` plus `get_game_state` (`test_live_tool_schemas_add_get_game_state`).

---

## run_agent(..., state_path, owned_towers)

```python
def run_agent(connection, client, round_number, money, difficulty="medium", max_iterations=8, state_path: Path | None = None, owned_towers: Sequence[PlacedTower] | None = None) -> AgentResult
```

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`state_path`|A) Live run|A1: Given|state file path|
|||A2: None|`None`|
|`owned_towers`|B) Owned towers|B1: One known|`LIVE_STATE.towers`|
|||B2: Known and unknown|Super Monkey `2-0-0` and `PlacedTower("BananaFarm", None, "2-0-0", False)`|
|||B3: Empty|`()`|
|||B4: None|`None`|

Base case: A1, B1

### Base Choice Coverage

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | user message `Round 63, money $100000, difficulty medium. You own: Super Monkey 2-0-0. Recommend what to buy.`; system message is `SYSTEM_PROMPT + "\n" + LIVE_PROMPT`; tools are `LIVE_TOOL_SCHEMAS`; a scripted `get_game_state` call returns round 63 | `test_run_agent_live_all_base` |
| T2 | A2 | B1 | tools are `TOOL_SCHEMAS`; system message is `SYSTEM_PROMPT` | `test_run_agent_live_no_state_path` |
| T3 | A1 | B2 | user message contains `You own: Super Monkey 2-0-0, BananaFarm 2-0-0 (not in the database).` | `test_run_agent_live_unknown_tower` |
| T4 | A1 | B3 | user message contains `You own no towers.` | `test_run_agent_live_no_towers` |
| T5 | A1 | B4 | user message is `Round 63, money $100000, difficulty medium. Recommend what to buy.` | `test_run_agent_live_owned_none` |

Offline eval (not BCC): `tests/agent_evals/test_offline_live_eval.py` runs a stub that calls `get_game_state`, then `recommend` with the state's round, money and difficulty; all standard checks pass against the state's money.
