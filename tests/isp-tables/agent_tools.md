# Agent tools: `call_tool` and `TOOL_SCHEMAS`

## Rules for these tests

- Contract: `docs/agent.md` ("Tools", "Error shape", "Filter properties"). Module: `btd6/agent/tools.py`.
- Fixture: `tests/recommend_fixture.py::build_recommend_database()` (four Super Monkey upgrades with costs, rounds 1-100 plus camo round 101). Medium costs: `0-0-0` 2500, `1-0-0` 4500, `3-0-0` 27000, `0-0-4` 67855. Only `0-0-4` hits camo; lead is popped by `3-0-0` and `0-0-4`.
- `call_tool` never raises for bad input. It returns `{"error": {"type": <exception class name>, "message": str}}`.
- Every result must satisfy `json.dumps(result, allow_nan=False)` (NaN becomes `null`).
- Floats are compared with `pytest.approx(rel=1e-6)`.

---

## call_tool

```python
def call_tool(connection: sqlite3.Connection, name: str, arguments: dict) -> dict
```

Dispatches to one of five tools and returns a JSON-serializable dict, or an error dict.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`name`|A) Tool name|A1: `get_round_threats`|`"get_round_threats"`|
|||A2: `search_upgrades`|`"search_upgrades"`|
|||A3: `rank_upgrades`|`"rank_upgrades"`|
|||A4: `recommend`|`"recommend"`|
|||A5: `total_cost`|`"total_cost"`|
|||A6: Unknown|`"delete_everything"`|
|`arguments`|B) Argument names and presence|B1: Valid and complete|per tool, see below|
|||B2: Unknown argument name|`{"round": 63, "colour": "red"}`|
|||B3: Required argument missing|`{}`|
|`arguments`|C) Argument value validity|C1: Valid|per tool|
|||C2: Wrong type|`{"round": "63"}`|
|||C3: Invalid value for the library (bad metric, difficulty, path, negative money, unknown tower, limit 0)|`{"round": 1, "money": -1}`|
|||C4: Round outside the loaded range|`{"round": 150}`|
|`connection` (state)|D) Data loaded|D1: Upgrades, costs and rounds|`build_recommend_database()`|
|||D2: No rounds loaded|`build_recommend_database(with_rounds=False)`|
|||D3: Costs not loaded|`build_recommend_database(with_costs=False)`|

Valid calls used as base per tool: `get_round_threats {"round": 63}`; `search_upgrades {"tower_name": "Super Monkey", "can_hit_camo": true, "limit": 1}`; `rank_upgrades {"filters": {"tower_name": "Super Monkey"}, "metric": "dps", "limit": 2}`; `recommend {"round": 63, "money": 100000}`; `total_cost {"tower_name": "Super Monkey", "path": "1-0-0"}`.

Base case: A4 (`recommend`), B1, C1, D1

### Base Choice Coverage

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A4 | B1 | C1 | D1 | `recommendations` paths `["3-0-0", "0-0-4"]`, `reasons` lists, JSON strict | `test_call_tool_recommend_all_base` |
| T2 | A1 | B1 | C1 | D1 | `round` 63, `property_share["lead"]` 0.1197, `camo_share` 0.0 | `test_call_tool_get_round_threats_valid` |
| T3 | A2 | B1 | C1 | D1 | one row, `path` `"0-0-4"`, `can_hit_camo` is `True` | `test_call_tool_search_upgrades_valid` |
| T4 | A3 | B1 | C1 | D1 | paths `["3-0-0", "0-0-4"]`, rows trimmed to the ten documented keys | `test_call_tool_rank_upgrades_valid` |
| T5 | A5 | B1 | C1 | D1 | `{"tower_name": "Super Monkey", "path": "1-0-0", "difficulty": "medium", "total_cost": 4500}` | `test_call_tool_total_cost_valid` |
| T6 | A6 | B1 | C1 | D1 | `error.type == "UnknownTool"`, no exception | `test_call_tool_unknown_tool` |
| T7 | A4 | B2 | C1 | D1 | `error.type == "TypeError"` | `test_call_tool_unknown_argument` |
| T8 | A4 | B3 | C1 | D1 | `error.type == "TypeError"` | `test_call_tool_missing_required_argument` |
| T9 | A1 | B1 | C2 | D1 | `error.type == "TypeError"` | `test_call_tool_get_round_threats_wrong_type` |
| T10 | A4 | B1 | C3 | D1 | `error.type == "QueryError"` | `test_call_tool_recommend_negative_money` |
| T11 | A1 | B1 | C4 | D1 | `error.type == "ValueError"` | `test_call_tool_get_round_threats_out_of_range` |
| T12 | A4 | B1 | C1 | D2 | `error.type == "NoRoundDataError"` | `test_call_tool_recommend_no_rounds` |
| T13 | A3 | B1 | C1 | D3 | rows have `total_cost` `None`, strict JSON succeeds (no NaN) | `test_call_tool_rank_upgrades_costs_not_loaded` |

### Per-tool invalid-input rows (one test each, non-BCC variations of C3/C4/B2/B3)

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T14 | `get_round_threats` round 0 | `ValueError` error | `test_call_tool_get_round_threats_round_zero` |
| T15 | `get_round_threats` no rounds loaded (D2) | `NoRoundDataError` error | `test_call_tool_get_round_threats_no_rounds` |
| T16 | `get_round_threats` round missing | `TypeError` error | `test_call_tool_get_round_threats_missing_round` |
| T17 | `search_upgrades` bad `sort_by` | `QueryError` error | `test_call_tool_search_upgrades_bad_sort` |
| T18 | `search_upgrades` limit 0 | `QueryError` error | `test_call_tool_search_upgrades_limit_zero` |
| T19 | `search_upgrades` unknown argument | `TypeError` error | `test_call_tool_search_upgrades_unknown_argument` |
| T20 | `search_upgrades` `limit` wrong type (`"1"`) | error present, no exception | `test_call_tool_search_upgrades_limit_wrong_type` |
| T21 | `rank_upgrades` bad metric | `QueryError` error | `test_call_tool_rank_upgrades_bad_metric` |
| T22 | `rank_upgrades` bad difficulty | `QueryError` error | `test_call_tool_rank_upgrades_bad_difficulty` |
| T23 | `rank_upgrades` unknown filter name | `TypeError` error | `test_call_tool_rank_upgrades_unknown_filter` |
| T24 | `rank_upgrades` limit 0 | `QueryError` error | `test_call_tool_rank_upgrades_limit_zero` |
| T25 | `recommend` bad difficulty | `QueryError` error | `test_call_tool_recommend_bad_difficulty` |
| T26 | `recommend` round not loaded (150) | `QueryError` error | `test_call_tool_recommend_round_not_loaded` |
| T27 | `recommend` money wrong type (`"5000"`) | error present (`TypeError` or `QueryError`) | `test_call_tool_recommend_money_wrong_type` |
| T28 | `recommend` missing `money` | `TypeError` error | `test_call_tool_recommend_missing_money` |
| T29 | `total_cost` path `9-0-0` | `QueryError` error | `test_call_tool_total_cost_bad_path` |
| T30 | `total_cost` unknown tower | `QueryError` error | `test_call_tool_total_cost_unknown_tower` |
| T31 | `total_cost` bad difficulty | `QueryError` error | `test_call_tool_total_cost_bad_difficulty` |
| T32 | `total_cost` missing `path` | `TypeError` error | `test_call_tool_total_cost_missing_path` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T33 | `recommend` empty result (money 2499) | `{"recommendations": []}` | `test_call_tool_recommend_money_too_low` |
| T34 | `recommend` default limit 5 and `limit` argument | round 1 gives 4 rows; `limit` 1 gives `["3-0-0"]` | `test_call_tool_recommend_limit` |
| T35 | `recommend` camo round | `["0-0-4"]`, reasons start `["affordable", "hits_camo"]` | `test_call_tool_recommend_camo_round` |
| T36 | `recommend` difficulty | easy `0-0-0` cost 2125 | `test_call_tool_recommend_easy_cost` |
| T37 | boolean flags | every `can_hit_camo` / `can_pop_*` in search rows is `bool` | `test_call_tool_search_upgrades_flags_are_booleans` |
| T38 | rank `can_hit_camo` | `bool` | `test_call_tool_rank_upgrades_camo_is_boolean` |
| T39 | `total_cost` integer type and difficulty echoed | `isinstance(total_cost, int)`, `difficulty == "easy"`, cost 2125 for `0-0-0` | `test_call_tool_total_cost_easy` |
| T40 | `total_cost` costs not loaded (D3) | `total_cost` is `None` | `test_call_tool_total_cost_costs_not_loaded` |
| T41 | `search_upgrades` filters AND with `tower_name_contains` | no match gives `{"upgrades": []}` | `test_call_tool_search_upgrades_no_match` |
| T42 | hypothesis: any tool and any JSON-like arguments | never raises; result is a dict that passes strict `json.dumps` | `test_call_tool_never_raises` |
| T43 | hypothesis: `recommend` budget | every `total_cost <= money` | `test_call_tool_recommend_never_exceeds_money` |

---

## TOOL_SCHEMAS

```python
TOOL_SCHEMAS: list[dict]
```

The five tool definitions in OpenAI function-calling format.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`TOOL_SCHEMAS`|A) Entry structure|A1: Each entry is `{"type": "function", "function": {name, description, parameters}}`|all five entries|
|`TOOL_SCHEMAS`|B) Tool set|B1: Names equal the documented five|`get_round_threats, search_upgrades, rank_upgrades, recommend, total_cost`|
|`parameters`|C) Required list|C1: Matches the doc|`round`; none; none; `round, money`; `tower_name, path`|
|`metric` enum|D) Metric values|D1: Equal to `METRICS`|`btd6.ranking.METRICS`|
|`difficulty` enum|E) Difficulty values|E1: Equal to `DIFFICULTY_MULTIPLIERS` keys|`("easy", "medium", "hard", "impoppable")`|
|`parameters`|F) Consistency with `call_tool`|F1: Every schema name is dispatchable (not `UnknownTool`)|each name called with its valid arguments|

Base case: A1, B1, C1, D1, E1, F1 (each characteristic has one block, so each is one test)

### Base Choice Coverage

| BCC Test | Oracle | Test Name |
|---|---|---|
| T1 | `len == 5`, every entry has the OpenAI shape and `parameters["type"] == "object"` | `test_tool_schemas_openai_shape` |
| T2 | names in order equal the five documented names | `test_tool_schemas_names` |
| T3 | `required` equals the doc per tool (absent or empty for search and rank) | `test_tool_schemas_required` |
| T4 | `rank_upgrades` `metric` enum equals `list(METRICS)` | `test_tool_schemas_metric_enum` |
| T5 | `difficulty` enum of rank, recommend and total_cost equals `list(DIFFICULTY_MULTIPLIERS)` | `test_tool_schemas_difficulty_enum` |
| T6 | every schema is `json.dumps`-able; every description is a non-empty string | `test_tool_schemas_json_serializable` |
| T7 | calling each tool by schema name does not give `UnknownTool` | `test_tool_schemas_names_are_dispatchable` |
| T8 | `search_upgrades` and `rank_upgrades["filters"]` expose the 14 filter properties | `test_tool_schemas_filter_properties` |
