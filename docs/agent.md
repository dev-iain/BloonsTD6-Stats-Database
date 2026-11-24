# Agent: tools, schemas and delivery

Epic #125. An LLM is given a round and the player's money. It calls tools that are backed by the database and the recommender, then explains its pick. **The model never produces game numbers itself.** Every number in the answer comes from a tool result.

Modules:

- `btd6/agent/schemas.py`: `TOOL_SCHEMAS` and the shared filter properties (re-exported by `tools.py`).
- `btd6/agent/tools.py`: one wrapper per tool, `call_tool(connection, name, arguments) -> dict`, `execute_call` and `ToolCall`.
- `btd6/agent/client.py`: the OpenAI-compatible chat client, `client_from_environment` and the client errors.
- `btd6/agent/picks.py`: `Pick`, `AgentResult` and `parse_picks`.
- `btd6/agent/loop.py`: the tool loop (`run_agent`), `ChatClient` and the system prompt.
- CLI: `python -m btd6 agent --round N --money X [--difficulty D] [--max-iterations K]`, or `agent --live [--max-age S]` to take round, money and difficulty from the live game state (`docs/game-state.md`).

Tests: `tests/isp-tables/agent_tools.md`, `tests/isp-tables/agent_loop.md`, and evals in `tests/agent_evals/`.

## Delivery: direct tool loop on a free OpenAI-compatible API

| | MCP server | Direct tool loop (chosen) |
|---|---|---|
| Model cost | Needs an MCP-capable client. Claude Desktop and Claude Code use a paid Claude model | Any free OpenAI-compatible endpoint (Gemini free tier by default) |
| Reuse by the mod overlay (#139) | The overlay would have to host an MCP client | The overlay calls `GET /api/recommendations`, or `run_agent` behind a future endpoint (#137) |
| Testing without a key | Needs an MCP client harness | A stub client returns scripted messages, so `run_agent` is tested directly |
| Dependencies | `mcp` | None. HTTP goes through `requests`, which is already a dependency |

The tool layer (`tools.py`) does not depend on the delivery. An MCP server can wrap `TOOL_SCHEMAS` and `call_tool` later without changing them.

### Provider and model

| Environment variable | Required | Default | Meaning |
|---|---|---|---|
| `GEMINI_API_KEY` | yes | none | API key. It is read from the environment only; keep it in a gitignored `.env` and load it with `uv run --env-file .env` |
| `BTD6_AGENT_MODEL` | no | `gemini-3.5-flash-lite` | Model id |
| `BTD6_AGENT_BASE_URL` | no | `https://generativelanguage.googleapis.com/v1beta/openai/` | OpenAI-compatible base URL. The client posts to `{base}chat/completions` |

- `gemini-3.5-flash-lite` is a stable model and is free of charge on the Gemini API free tier. This was checked against the Gemini models and pricing pages on 2026-11-24.
- It is the default because `gemini-3.8-flash` (also free) returned HTTP 503 "high demand" and timed out in a live run on 2026-11-24, while `gemini-3.5-flash-lite` answered a full round-63 run in about 2 seconds.
- The free tier is rate-limited per project. Over the limit the API returns HTTP 429, and free-tier prompts may be used to improve Google's products.
- `gemini-3.8-flash` is a stronger free alternative when it is not overloaded.
- **Retries:** HTTP 429, 500, 502, 503 and 504, timeouts and connection errors are retried after 2 s and then 5 s (at most 3 attempts, `REQUEST_TIMEOUT_SECONDS` = 30 per attempt). After the last attempt the client raises `AgentError` naming the model and the cause and suggesting `BTD6_AGENT_MODEL`. HTTP 401 and 403 fail at once with a message about the API key. Other non-2xx statuses and other `requests` errors fail at once as `AgentError`. The CLI prints the message and exits with code 1.
- Any OpenAI-compatible provider works, for example Groq or OpenRouter free models. Set `BTD6_AGENT_BASE_URL` and `BTD6_AGENT_MODEL`, and put that provider's key in `GEMINI_API_KEY`.
- If the key is missing, the CLI prints `GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey and export it.` to stderr and exits with code 2.

## Loop

`run_agent(connection, client, round_number, money, difficulty="medium", max_iterations=8) -> AgentResult`

1. The messages start as `[system, user]`. The user message is `Round {round}, money ${money}, difficulty {difficulty}. Recommend what to buy.`
2. Call `client.complete(messages, TOOL_SCHEMAS)`. It returns one assistant message in OpenAI chat format: `{"role": "assistant", "content": str | None, "tool_calls": [...] | None}`.
3. If the message has `tool_calls`:
   - Append the assistant message.
   - For each call, run `call_tool`. If the arguments are not valid JSON, the call gets an `ArgumentError` result instead.
   - Append `{"role": "tool", "tool_call_id": id, "content": json.dumps(result)}`.
   - Record `ToolCall(name, arguments, result)`.
   - Go to step 2.
4. If the message has no `tool_calls`, its `content` is the final answer. Return `AgentResult(answer, tool_calls, picks=parse_picks(answer))`.
5. Each call to `client.complete` is one iteration. If `max_iterations` calls happen without a final answer, raise `AgentError("No final answer after {max_iterations} iterations")`.

Tool errors are not exceptions. They go back to the model as the tool result, so it can correct the call or report the problem.

### `AgentResult`

| Field | Type | Meaning |
|---|---|---|
| `answer` | `str` | The model's final text |
| `tool_calls` | `tuple[ToolCall, ...]` | Every tool call, in order |
| `picks` | `tuple[Pick, ...]` | Parsed from the answer's `Picks:` block |

- `ToolCall` is a frozen dataclass of `name: str`, `arguments: dict` and `result: dict`.
- `Pick` is a frozen dataclass of `tower_name: str`, `path: str` and `total_cost: int`.

### `parse_picks(answer)`

- Only the text after the last line equal to `Picks:` (case-insensitive, trimmed) is read.
- Each line matching `- <tower name> <X-Y-Z> $<cost>` becomes a `Pick`. Commas in the cost are allowed.
- `- none` means no picks.
- If there is no `Picks:` line, the result is `()`.

## System prompt

```
You are a Bloons TD6 advisor. You only know what the tools return.
1. Call get_round_threats for the round first.
2. Call recommend with the round, money and difficulty to get affordable candidates. Use rank_upgrades or search_upgrades only to compare alternatives.
3. Check every pick's cost against the money with total_cost or the cost in the tool result. Never pick something that costs more than the money.
4. Explain in a few sentences why the picks fit the round's threats (camo, lead, MOAB share, pierce).
Never state a number, tower or upgrade path that did not come from a tool result. If a tool returns an error, say so and do not make up data. If nothing is affordable, say so plainly.
End the answer with a line "Picks:" followed by one line per pick in the form "- <tower name> <X-Y-Z> $<total cost>", or "- none".
```

## Tools

Shared rules:

- Arguments are a JSON object. Unknown argument names and missing required arguments return a `TypeError` error.
- Numbers in results are JSON numbers. NaN becomes `null`.
- `can_hit_camo` and `can_pop_*` are returned as booleans, or `null` when unknown.

### Error shape

```json
{"error": {"type": "QueryError", "message": "Unknown difficulty: 'nightmare'"}}
```

| `type` | Cause |
|---|---|
| `QueryError` | Invalid input from the library: bad metric, difficulty, path, negative money, unknown tower in `total_cost`, and so on |
| `NoRoundDataError` | No rounds are loaded |
| `ValueError` | The round is out of the loaded range (`get_round_threats`) |
| `TypeError` | Wrong argument types, unknown argument names or missing required arguments |
| `ProgrammingError` (or another `sqlite3.Error` subclass) | SQLite rejected an argument value, for example a nested object passed as a filter value |
| `UnknownTool` | The tool name is not in `TOOL_SCHEMAS` |
| `ArgumentError` | The arguments string is not valid JSON (set by the loop) |

### Filter properties (shared by `search_upgrades` and `rank_upgrades`)

These are the `UpgradeFilters` fields (`docs/queries.md`). All are optional.

```json
{
  "tower_name": {"type": "string", "description": "Exact tower name, e.g. \"Super Monkey\""},
  "tower_name_contains": {"type": "string"},
  "category": {"type": "string", "description": "Tower category, e.g. \"Magic\""},
  "can_pop_lead": {"type": "boolean"}, "can_pop_black": {"type": "boolean"},
  "can_pop_white": {"type": "boolean"}, "can_pop_purple": {"type": "boolean"},
  "can_pop_glass": {"type": "boolean"}, "can_pop_frozen": {"type": "boolean"},
  "can_hit_camo": {"type": "boolean"},
  "min_range": {"type": "number", "minimum": 0},
  "min_pierce": {"type": "number", "minimum": 0},
  "min_damage": {"type": "number", "minimum": 0},
  "min_projectile_speed": {"type": "number", "minimum": 0},
  "damage_type": {"type": "string", "description": "Damage type name, e.g. \"Normal\", \"Plasma\""}
}
```

### `get_round_threats`

Description: "What a round contains: total RBE (red bloon equivalent) and the share of RBE that is camo, regrow, MOAB-class and each pop property (lead, black, white, purple, glass, frozen). Call this first."

```json
{"type": "object",
 "properties": {"round": {"type": "integer", "minimum": 1, "maximum": 100}},
 "required": ["round"]}
```

Result: the fields of `RoundThreats` (`docs/threats.md`).

- Call: `{"round": 63}`
- Result: `{"round": 63, "total_rbe": 13740, "unknown_groups": 0, "property_share": {"lead": 0.1197, "black": 0.0, "white": 0.0, "purple": 0.0, "glass": 0.0, "frozen": 0.0}, "camo_share": 0.0, "regrow_share": 0.0, "moab_share": 0.0, "mean_layers": 22.9}` (the values are illustrative)

### `search_upgrades`

Description: "Find upgrades by stats. Filters combine with AND. Returns raw stats of each upgrade's main attack."

```json
{"type": "object",
 "properties": {"...filter properties...",
   "sort_by": {"type": "string", "enum": ["range", "attack_rate", "projectile_damage", "projectile_pierce", "projectile_speed", "projectile_count", "ability_cooldown", "path"]},
   "descending": {"type": "boolean", "default": true},
   "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}}
```

Result: `{"upgrades": [row, ...]}`. Each row has the `search_upgrades` columns (`docs/queries.md`).

- Call: `{"tower_name": "Super Monkey", "can_hit_camo": true, "limit": 1}`
- Result: `{"upgrades": [{"tower_name": "Super Monkey", "category": "Magic", "path": "0-0-4", "range": 50.0, "attack_rate": 0.045, "projectile_count": 1, "projectile_damage": 1.0, "projectile_pierce": 2.0, "projectile_speed": 300.0, "projectile_radius": 3.0, "projectile_lifespan": 1.0, "footprint_radius": 9.0, "can_hit_camo": true, "ability_cooldown": null, "damage_type": "Normal", "can_pop_lead": true, "can_pop_black": true, "can_pop_white": true, "can_pop_purple": true, "can_pop_glass": true, "can_pop_frozen": true}]}`

### `rank_upgrades`

Description: "Rank upgrades by a derived metric (dps, moab_dps, damage_per_dollar, pierce_damage_per_dollar) with difficulty-adjusted total cost."

```json
{"type": "object",
 "properties": {
   "filters": {"type": "object", "properties": {"...filter properties..."}},
   "metric": {"type": "string", "enum": ["dps", "moab_dps", "damage_per_dollar", "pierce_damage_per_dollar"], "default": "damage_per_dollar"},
   "difficulty": {"type": "string", "enum": ["easy", "medium", "hard", "impoppable"], "default": "medium"},
   "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}}
```

- Result: `{"upgrades": [...]}`.
- Each row has only `tower_name`, `path`, `total_cost`, `dps`, `moab_dps`, `pierce_weighted_dps`, `damage_per_dollar`, `pierce_damage_per_dollar`, `projectile_pierce` and `can_hit_camo`. The columns are trimmed to save tokens.
- `total_cost` is an integer or `null`.
- Call: `{"filters": {"tower_name": "Super Monkey"}, "metric": "dps", "limit": 1}`
- Result: `{"upgrades": [{"tower_name": "Super Monkey", "path": "3-0-0", "total_cost": 27000, "dps": 1066.7, "moab_dps": 1066.7, "pierce_weighted_dps": 6400.0, "damage_per_dollar": 0.0395, "pierce_damage_per_dollar": 0.237, "projectile_pierce": 6.0, "can_hit_camo": false}]}` (the values are illustrative)

### `recommend`

Description: "Affordable upgrades that can pop everything the round contains (camo, lead, ...), ranked by round-fit score per dollar. Reasons explain each match."

```json
{"type": "object",
 "properties": {
   "round": {"type": "integer", "minimum": 1, "maximum": 100},
   "money": {"type": "integer", "minimum": 0},
   "difficulty": {"type": "string", "enum": ["easy", "medium", "hard", "impoppable"], "default": "medium"},
   "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5}},
 "required": ["round", "money"]}
```

- Result: `{"recommendations": [Recommendation, ...]}`. The fields are those of `Recommendation` (`docs/recommend.md`), and `reasons` is a list.
- An empty list means nothing affordable can handle the round.
- Call: `{"round": 63, "money": 100000}`
- Result: `{"recommendations": [{"tower_name": "Super Monkey", "path": "0-0-4", "total_cost": 67855, "score": 0.0123, "dps": 22.2, "moab_dps": 22.2, "pierce_weighted_dps": 44.4, "projectile_pierce": 2.0, "reasons": ["affordable", "pops_lead"]}]}` (the values are illustrative)

### `total_cost`

Description: "Total cost (base plus every tier on the path) of an upgrade at a difficulty."

```json
{"type": "object",
 "properties": {
   "tower_name": {"type": "string"},
   "path": {"type": "string", "pattern": "^[0-5]-[0-5]-[0-5]$"},
   "difficulty": {"type": "string", "enum": ["easy", "medium", "hard", "impoppable"], "default": "medium"}},
 "required": ["tower_name", "path"]}
```

- Result: `{"tower_name": ..., "path": ..., "difficulty": ..., "total_cost": int | null}`. The cost is `null` when costs are not loaded for that tower.
- Call: `{"tower_name": "Super Monkey", "path": "1-0-0"}`
- Result: `{"tower_name": "Super Monkey", "path": "1-0-0", "difficulty": "medium", "total_cost": 4500}`
- Call: `{"tower_name": "Super Monkey", "path": "9-0-0"}`
- Result: `{"error": {"type": "QueryError", "message": "..."}}`

### `get_game_state` (live runs only)

Offered only when `run_agent` gets a `state_path` (`agent --live`); the schemas are then `LIVE_TOOL_SCHEMAS` (`TOOL_SCHEMAS` plus this one).

Description: "The live game as the mod last reported it: round, cash (money), lives, difficulty, map and the towers already placed (tower_name, path X-Y-Z; known is false for towers that are not in the database). Call it when cash or towers may have changed."

```json
{"type": "object", "properties": {}}
```

- Result: `state_summary` from `btd6/game_state.py`: `{"round": 63, "money": 8000, "lives": 150, "difficulty": "medium", "mode": "Standard", "map": "...", "towers": [{"base_id": "DartMonkey", "tower_name": "Dart Monkey", "path": "0-2-3", "known": true}], "received_at": "...", "age_seconds": 1.2, "stale": false}`.
- Errors: `NoGameStateError` (no file), `StaleGameStateError` (older than 30 s), `GameStateError` (corrupt file), `TypeError` (any argument), and `LiveStateUnavailable` when the run is not live.

## Live runs

`run_agent(..., state_path=None, owned_towers=None)`:

- With `owned_towers` (a sequence of `PlacedTower`), the user message gains `You own: Super Monkey 2-0-0, BananaFarm 2-0-0 (not in the database).` (or `You own no towers.`) before `Recommend what to buy.`
- With `state_path`, the system message is `SYSTEM_PROMPT + "\n" + LIVE_PROMPT`, the tools are `LIVE_TOOL_SCHEMAS`, and `get_game_state` reads that file. `LIVE_PROMPT` tells the model that the owned towers are already placed, to mention upgrades to them in the explanation, and to list only new purchases under `Picks:`.

## Evaluation (`tests/agent_evals/`)

- Scenarios are data in `scenarios.json`: `round`, `money`, `difficulty` and the expectations.
- Checks on every run:
  - Every pick `(tower_name, path)` appears in a tool result from that run.
  - Every pick's `total_cost` is at most the money.
  - Every picked tower exists in the `towers` table.
- Scenario expectations:
  - Round 63 with enough money: picks can hit camo or pop lead, and `pierce_weighted_dps` is non-null.
  - Round 40: a pick has a non-null `moab_dps`.
  - Very low money: `picks == ()`.
  - Unloaded round: the answer mentions the error, and `picks == ()`.
- Live game state: `test_offline_live_eval.py` runs a stub that calls `get_game_state` and then `recommend` with the state's round and money, and must pass every check above; the live suite has the same scenario (`test_live_state_scenario`).
- Offline runs use a scripted stub client and are part of `uv run pytest`.
- Live runs (`uv run pytest -m live_agent`) need `GEMINI_API_KEY` and the real `btd6.db`. They are skipped by default.
