# Agent loop: `run_agent`, `parse_picks`, `client_from_environment`, `OpenAICompatibleClient.complete`, `agent` command

## Rules for these tests

- Contract: `docs/agent.md` (sections Delivery, Provider and model, Loop, AgentResult, parse_picks, System prompt).
- The model is replaced by `ScriptedClient` (`tests/agent_stub.py`); HTTP by a fake session. No network.
- Database: `build_recommend_database()` (`tests/recommend_fixture.py`), real tool results come from `call_tool`.
- Tool failures are results, not exceptions. Only the iteration cap and HTTP failures raise `AgentError`.

---

## run_agent

```python
def run_agent(connection, client, round_number: int, money: int, difficulty: str = "medium", max_iterations: int = 8) -> AgentResult
```

Runs the tool loop until the model answers without tool calls.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`client`|A) Script shape|A1: Tools then final answer|threats, recommend, answer|
|||A2: Final answer immediately|answer only|
|||A3: Always requests tools|repeat `get_round_threats`|
|||A4: Several calls in one message|threats + total_cost|
|`client`|B) Tool call validity|B1: Valid arguments|`{"round": 63}`|
|||B2: Tool returns an error|`difficulty="nightmare"`|
|||B3: Arguments not JSON|`"{not json"`|
|||B4: Unknown tool|`fly_to_moon`|
|`max_iterations`|C) Cap relative to calls needed|C1: Above (default 8)|`8`|
|||C2: Exactly enough|`2` for one tool + answer|
|||C3: Below|`1`..`3` with endless tools|
|`difficulty`|D) Difficulty|D1: Default|omitted|
|||D2: Given|`"hard"`|

Base case: A1, B1, C1, D1

### Base Choice Coverage

| BCC Test | A | B | C | D | Oracle | Test Name |
|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | answer returned, two `ToolCall`s in order with `call_tool` results, picks parsed, 3 `complete` calls, tool messages have role `tool` and matching id | `test_run_agent_full_flow`, `test_run_agent_tool_result_messages` |
| T2 | A2 | B1 | C1 | D1 | no tool calls, 1 `complete` call | `test_run_agent_immediate_final_answer` |
| T3 | A3 | B1 | C1 | D1 | `AgentError` after exactly 8 calls | `test_run_agent_default_cap_is_eight` |
| T4 | A4 | B1 | C1 | D1 | both recorded, ids `call_1`, `call_2` | `test_run_agent_several_calls_in_one_message` |
| T5 | A1 | B2 | C1 | D1 | error content sent to model, loop continues | `test_run_agent_tool_error_goes_back_to_model` |
| T6 | A1 | B3 | C1 | D1 | `ArgumentError` result, loop continues | `test_run_agent_invalid_json_arguments` |
| T7 | A1 | B4 | C1 | D1 | `UnknownTool` result | `test_run_agent_unknown_tool_is_an_error_result` |
| T8 | A1 | B1 | C2 | D1 | answer returned, no error | `test_run_agent_final_answer_on_last_allowed_iteration` |
| T9 | A3 | B1 | C3 | D1 | `AgentError("No final answer after N iterations")`, N calls | `test_run_agent_iteration_cap` |
| T10 | A2 | B1 | C1 | D2 | user message `Round 63, money $5000, difficulty hard. Recommend what to buy.`, system message is `SYSTEM_PROMPT`, tools are `TOOL_SCHEMAS` | `test_run_agent_initial_messages` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T11 | D1 | user message says `difficulty medium` | `test_run_agent_default_difficulty_is_medium` |
| T12 | `tool_calls == []` | treated as a final answer | `test_run_agent_empty_tool_calls_list_is_final` |
| T13 | result types | `Pick`, `ToolCall`, `AgentResult` are frozen | `test_dataclasses_are_frozen` |
| T14 | system prompt | names the tools, `Picks:`, `- none` | `test_system_prompt_mentions` |

---

## parse_picks

```python
def parse_picks(answer: str) -> tuple[Pick, ...]
```

Reads the lines after the last `Picks:` line (trimmed, case-insensitive) into `Pick`s.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`answer`|A) Picks header|A1: One header|`Picks:`|
|||A2: No header|prose only|
|||A3: Several headers|two `Picks:` blocks|
|||A4: Different case or padding|`PICKS:`, `  Picks:  `|
|||A5: Header inside a longer line|`My Picks: `|
|`answer`|B) Block content|B1: One pick|`- Super Monkey 3-0-0 $27000`|
|||B2: Several picks|two lines|
|||B3: `- none`|`- none`|
|||B4: Empty block|nothing after header|
|||B5: Non-matching lines mixed in|prose, bad path|
|`answer`|C) Cost format|C1: Plain digits|`$27000`|
|||C2: Thousands commas|`$67,855`, `$1,234,567`|

Base case: A1, B1, C1

### Base Choice Coverage

| BCC Test | A | B | C | Oracle | Test Name |
|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | one `Pick("Super Monkey", "3-0-0", 27000)` | `test_parse_picks[single]` |
| T2 | A2 | B1 | C1 | `()` | `test_parse_picks[no_header]` |
| T3 | A3 | B1 | C1 | only the last block | `test_parse_picks[last_block_only]` |
| T4 | A4 | B1 | C1 | pick parsed | `test_parse_picks[upper_case_header]`, `[lower_case_header]`, `[padded_header]` |
| T5 | A5 | B1 | C1 | `()` | `test_parse_picks_header_must_be_whole_line` |
| T6 | A1 | B2 | C1 | two picks in order | `test_parse_picks[multiple]` |
| T7 | A1 | B3 | C1 | `()` | `test_parse_picks[none]` |
| T8 | A1 | B4 | C1 | `()` | `test_parse_picks[empty_block]` |
| T9 | A1 | B5 | C1 | matching lines only | `test_parse_picks[trailing_prose]`, `[malformed_path]` |
| T10 | A1 | B1 | C2 | cost `67855` | `test_parse_picks[comma_cost]` |

### Properties (hypothesis)

- Formatting any list of picks (with `{:,}` costs) after `Picks:` parses back to the same tuple (`test_parse_picks_round_trips`).
- Any text returns a tuple of `Pick` and never raises (`test_parse_picks_is_total`).

---

## client_from_environment

```python
def client_from_environment(environ: Mapping[str, str]) -> OpenAICompatibleClient
```

Builds the client from `GEMINI_API_KEY`, `BTD6_AGENT_MODEL`, `BTD6_AGENT_BASE_URL`.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|`environ`|A) API key|A1: Present|`"secret"`|
|||A2: Absent|`{}`|
|||A3: Empty|`""`|
|||A4: Whitespace only|`"   "`|
|`environ`|B) Model and base URL|B1: Both absent (defaults)|`{}`|
|||B2: Both set|`other-model`, `https://example.test/v1/`|

Base case: A1, B1

### Base Choice Coverage

| BCC Test | A | B | Oracle | Test Name |
|---|---|---|---|---|
| T1 | A1 | B1 | key `secret`, `DEFAULT_MODEL`, `DEFAULT_BASE_URL` | `test_client_from_environment_defaults` |
| T2 | A2 | B1 | `MissingApiKeyError` (an `AgentError`) naming `GEMINI_API_KEY` | `test_client_from_environment_missing_key[environ0]` |
| T3 | A3 | B1 | same | `test_client_from_environment_missing_key[environ1]` |
| T4 | A4 | B1 | same | `test_client_from_environment_missing_key[environ2]` |
| T5 | A1 | B2 | model and base URL taken from the environment | `test_client_from_environment_overrides` |

---

## OpenAICompatibleClient.complete

```python
def complete(self, messages: list[dict], tools: list[dict]) -> dict
```

Posts to `{base_url}chat/completions` (timeout `REQUEST_TIMEOUT_SECONDS` = 30) and returns `choices[0].message`.
Retries `RETRY_STATUSES` (429, 500, 502, 503, 504), `requests.Timeout` and `requests.ConnectionError` after `sleep(delay)` for each of `RETRY_DELAYS_SECONDS` (2.0, 5.0): at most 3 attempts.
Constructor: `OpenAICompatibleClient(api_key, model, base_url, session=None, sleep=None)`; `sleep` defaults to `time.sleep`. `DEFAULT_MODEL` is `gemini-3.5-flash-lite`.
Tests use `FakeSession` (scripted responses/exceptions, records calls) and `RecordingSleep`; no real sleeping.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|response|A) HTTP status|A1: 200|`200`|
|||A2: Other 2xx|`201`, `299`|
|||A3: Auth failure|`401`, `403`|
|||A4: Non-retryable client error|`400`, `404`, `422`|
|||A5: Retryable status|`429`, `500`, `502`, `503`, `504`|
|`session`|B) Transport outcome|B1: Response returned|`FakeResponse`|
|||B2: `requests.Timeout`|`Timeout("slow")`|
|||B3: `requests.ConnectionError`|`ConnectionError("down")`|
|||B4: Other `requests.RequestException`|`InvalidURL`|
|script|C) Failures before outcome|C1: None (first attempt succeeds)|`[200]`|
|||C2: One retryable failure then success|`[503, 200]`, `[Timeout, 200]`|
|||C3: Two retryable failures then success|`[429, 503, 200]`|
|||C4: Failure on every attempt|repeating `503` / `ConnectionError`|
|`session`|D) Session|D1: Fake session given|`FakeSession`|
|||D2: Omitted|default session created|
|`sleep`|E) Sleep|E1: Injected recorder|`RecordingSleep`|
|||E2: Omitted|`time.sleep`|

Base case: A1, B1, C1, D1, E1

### Base Choice Coverage

| BCC Test | A | B | C | D | E | Oracle | Test Name |
|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | URL, `Authorization: Bearer key`, body `{model, messages, tools}`, `timeout == REQUEST_TIMEOUT_SECONDS`, message returned | `test_complete_posts_openai_request` |
| T2 | A1 | B1 | C1 | D1 | E1 | one post, no sleep | `test_complete_success_first_try_does_not_sleep` |
| T3 | A2 | B1 | C1 | D1 | E1 | message returned | `test_complete_accepts_2xx` |
| T4 | A3 | B1 | C1 | D1 | E1 | `AgentError` mentions `API key` and `GEMINI_API_KEY`; 1 post, no sleep | `test_complete_auth_failure_mentions_api_key` |
| T5 | A4 | B1 | C1 | D1 | E1 | `AgentError` with `HTTP <status>` and body text; 1 post, no sleep | `test_complete_non_retryable_status_fails_immediately` |
| T6 | A5 | B1 | C4 | D1 | E1 | 3 posts, sleeps `[2.0, 5.0]`, `AgentError` names model, `HTTP <status>`, `3 attempts`, `BTD6_AGENT_MODEL` | `test_complete_retryable_status_exhausts_attempts` |
| T7 | A5 | B1 | C2 | D1 | E1 | 2 posts, sleeps `[2.0]`, message returned | `test_complete_retries_503_then_succeeds` |
| T8 | A5 | B1 | C3 | D1 | E1 | 3 posts, sleeps `[2.0, 5.0]`, message returned | `test_complete_retries_429_503_then_succeeds` |
| T9 | A1 | B2 | C2 | D1 | E1 | 2 posts, sleeps `[2.0]`, message returned | `test_complete_retries_timeout_then_succeeds` |
| T10 | A1 | B2 | C4 | D1 | E1 | `AgentError` says timed out / timeout | `test_complete_timeout_every_time_names_the_cause` |
| T11 | A1 | B3 | C4 | D1 | E1 | 3 posts, sleeps `[2.0, 5.0]`, `AgentError` with model and `BTD6_AGENT_MODEL` | `test_complete_connection_error_retries_then_raises_agent_error` |
| T12 | A1 | B4 | C1 | D1 | E1 | `AgentError` immediately, 1 post, no sleep | `test_complete_other_request_exception_is_agent_error` |
| T13 | A1 | B1 | C1 | D2 | E1 | `client.session is not None` | `test_complete_creates_default_session` |
| T14 | A1 | B1 | C1 | D1 | E2 | `client.sleep is time.sleep` | `test_complete_default_sleep_is_time_sleep` |

### Extra non-BCC tests

| Test | Covers | Oracle | Test Name |
|---|---|---|---|
| T15 | constants | `RETRY_STATUSES`, `RETRY_DELAYS_SECONDS`, `DEFAULT_MODEL`, `REQUEST_TIMEOUT_SECONDS` have the specified values | `test_retry_constants` |

---

## `agent` command

```
python -m btd6 --db PATH agent --round N --money X [--difficulty D] [--max-iterations K]
```

Builds the client with `btd6.cli.client_from_environment(os.environ)`, runs `run_agent`, prints the answer.

### ISP

|Parameter|Characteristic|Partition|Value|
|---|---|---|---|
|environment|A) API key|A1: Set|`test-key`|
|||A2: Unset|deleted|
|||A3: Blank|`"  "`|
|`--db`|B) Database file|B1: Exists|saved fixture|
|||B2: Missing|`missing.db`|
|`--difficulty`|C) Difficulty|C1: Omitted (medium)|none|
|||C2: Each valid choice|`easy`, `hard`, `impoppable`|
|||C3: Invalid|`nightmare`|
|`--max-iterations`|D) Iterations|D1: Omitted|none|
|||D2: Valid cap, never answered|`3`|
|||D3: Not an integer|`many`|
|client|E) Client outcome|E1: Answers|scripted answer|
|||E2: Raises `AgentError`|`HTTP 429 from provider`|
|||E3: Raises busy-model `AgentError`|message with `BTD6_AGENT_MODEL`|
|`--round`, `--money`|F) Required options|F1: Both present|`63`, `5000`|
|||F2: One missing|omit one|

Base case: A1, B1, C1, D1, E1, F1

### Base Choice Coverage

| BCC Test | A | B | C | D | E | F | Oracle | Test Name |
|---|---|---|---|---|---|---|---|---|
| T1 | A1 | B1 | C1 | D1 | E1 | F1 | exit 0, answer on stdout, stderr empty | `test_main_agent_prints_answer` |
| T2 | A2 | B1 | C1 | D1 | E1 | F1 | exit 2, stderr is the `GEMINI_API_KEY is not set...` message | `test_main_agent_missing_api_key` |
| T3 | A3 | B1 | C1 | D1 | E1 | F1 | exit 2, stderr names `GEMINI_API_KEY` | `test_main_agent_blank_api_key` |
| T4 | A1 | B2 | C1 | D1 | E1 | F1 | exit 1, `Database not found...`, client never called | `test_main_agent_database_missing` |
| T5 | A1 | B1 | C2 | D1 | E1 | F1 | user message carries the difficulty | `test_main_agent_difficulty_choices` |
| T6 | A1 | B1 | C3 | D1 | E1 | F1 | argparse exit 2, invalid choice | `test_main_agent_difficulty_invalid` |
| T7 | A1 | B1 | C1 | D2 | E1 | F1 | exit 1, `No final answer after 3 iterations` on stderr | `test_main_agent_max_iterations_option` |
| T8 | A1 | B1 | C1 | D3 | E1 | F1 | argparse exit 2 | `test_main_agent_max_iterations_not_integer` |
| T9 | A1 | B1 | C1 | D1 | E2 | F1 | exit 1, message on stderr, stdout empty | `test_main_agent_agent_error_from_client` |
| T10 | A1 | B1 | C1 | D1 | E1 | F2 | argparse exit 2 | `test_main_agent_required_options` |
| T11 | A1 | B1 | C1 | D1 | E3 | exit 1, `BTD6_AGENT_MODEL` on stderr, no `Unexpected error`, stdout empty | `test_main_agent_busy_model_error_is_a_clean_message` |
