from __future__ import annotations

import dataclasses
import json
import sqlite3
import time

import pytest
import requests
from hypothesis import given
from hypothesis import strategies as st

from btd6.agent import client as client_module
from btd6.agent.client import (
    API_KEY_VARIABLE,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    REQUEST_TIMEOUT_SECONDS,
    AgentError,
    MissingApiKeyError,
    OpenAICompatibleClient,
    client_from_environment,
)
from btd6.agent.loop import SYSTEM_PROMPT, run_agent
from btd6.agent.picks import AgentResult, Pick, parse_picks
from btd6.agent.tools import TOOL_SCHEMAS, ToolCall, call_tool
from tests.agent_stub import ScriptedClient, final_message, tool_call_message
from tests.recommend_fixture import build_recommend_database

ANSWER = "Lead round, so pierce matters.\nPicks:\n- Super Monkey 3-0-0 $27,000"


@pytest.fixture
def connection() -> sqlite3.Connection:
    database = build_recommend_database()
    yield database
    database.close()


def two_step_script() -> list[dict]:
    return [
        tool_call_message(("get_round_threats", {"round": 63})),
        tool_call_message(("recommend", {"round": 63, "money": 100000})),
        final_message(ANSWER),
    ]


# region run_agent


def test_run_agent_full_flow(connection: sqlite3.Connection) -> None:
    client = ScriptedClient(two_step_script())

    result = run_agent(connection, client, 63, 100000)

    assert isinstance(result, AgentResult)
    assert result.answer == ANSWER
    assert [call.name for call in result.tool_calls] == ["get_round_threats", "recommend"]
    assert result.tool_calls[0].arguments == {"round": 63}
    assert result.tool_calls[0].result == call_tool(connection, "get_round_threats", {"round": 63})
    recommend_args = {"round": 63, "money": 100000}
    assert result.tool_calls[1].result == call_tool(connection, "recommend", recommend_args)
    assert result.picks == (Pick("Super Monkey", "3-0-0", 27000),)
    assert client.call_count == 3


def test_run_agent_immediate_final_answer(connection: sqlite3.Connection) -> None:
    client = ScriptedClient([final_message("Nothing affordable.\nPicks:\n- none")])

    result = run_agent(connection, client, 63, 10)

    assert result.answer == "Nothing affordable.\nPicks:\n- none"
    assert result.tool_calls == ()
    assert result.picks == ()
    assert client.call_count == 1


def test_run_agent_initial_messages(connection: sqlite3.Connection) -> None:
    client = ScriptedClient([final_message("Picks:\n- none")])

    run_agent(connection, client, 63, 5000, "hard")

    messages, tools = client.requests[0]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert (
        messages[1]["content"] == "Round 63, money $5000, difficulty hard. Recommend what to buy."
    )
    assert tools == TOOL_SCHEMAS


def test_run_agent_default_difficulty_is_medium(connection: sqlite3.Connection) -> None:
    client = ScriptedClient([final_message("Picks:\n- none")])

    run_agent(connection, client, 1, 100)

    assert "difficulty medium" in client.requests[0][0][1]["content"]


def test_run_agent_tool_result_messages(connection: sqlite3.Connection) -> None:
    client = ScriptedClient(two_step_script())

    result = run_agent(connection, client, 63, 100000)

    messages, tools = client.requests[1]
    assert [message["role"] for message in messages] == ["system", "user", "assistant", "tool"]
    assert messages[2]["tool_calls"][0]["id"] == "call_1"
    assert messages[3]["tool_call_id"] == "call_1"
    assert json.loads(messages[3]["content"]) == json.loads(json.dumps(result.tool_calls[0].result))
    assert tools == TOOL_SCHEMAS
    last_messages = client.requests[2][0]
    assert [message["role"] for message in last_messages][-2:] == ["assistant", "tool"]


def test_run_agent_several_calls_in_one_message(connection: sqlite3.Connection) -> None:
    script = [
        tool_call_message(
            ("get_round_threats", {"round": 1}),
            ("total_cost", {"tower_name": "Super Monkey", "path": "1-0-0"}),
        ),
        final_message("Picks:\n- none"),
    ]
    client = ScriptedClient(script)

    result = run_agent(connection, client, 1, 100000)

    assert [call.name for call in result.tool_calls] == ["get_round_threats", "total_cost"]
    tool_messages = [message for message in client.requests[1][0] if message["role"] == "tool"]
    assert [message["tool_call_id"] for message in tool_messages] == ["call_1", "call_2"]


def test_run_agent_tool_error_goes_back_to_model(connection: sqlite3.Connection) -> None:
    bad_call = {"round": 63, "money": 100000, "difficulty": "nightmare"}
    client = ScriptedClient(
        [tool_call_message(("recommend", bad_call)), final_message("Tool failed.\nPicks:\n- none")]
    )

    result = run_agent(connection, client, 63, 100000)

    tool_message = client.requests[1][0][-1]
    assert tool_message["role"] == "tool"
    assert "error" in json.loads(tool_message["content"])
    assert "error" in tool_message["content"]
    assert "error" in result.tool_calls[0].result
    assert result.answer.startswith("Tool failed.")


def test_run_agent_unknown_tool_is_an_error_result(connection: sqlite3.Connection) -> None:
    client = ScriptedClient(
        [tool_call_message(("fly_to_moon", {})), final_message("Picks:\n- none")]
    )

    result = run_agent(connection, client, 1, 100)

    assert result.tool_calls[0].result["error"]["type"] == "UnknownTool"


@pytest.mark.parametrize("raw", ["{not json", "", "[1, 2"])
def test_run_agent_invalid_json_arguments(connection: sqlite3.Connection, raw: str) -> None:
    client = ScriptedClient(
        [tool_call_message(("recommend", raw)), final_message("Picks:\n- none")]
    )

    result = run_agent(connection, client, 63, 100000)

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].result["error"]["type"] == "ArgumentError"
    tool_message = client.requests[1][0][-1]
    assert json.loads(tool_message["content"])["error"]["type"] == "ArgumentError"
    assert "error" in tool_message["content"]


@pytest.mark.parametrize("max_iterations", [1, 3, 8])
def test_run_agent_iteration_cap(connection: sqlite3.Connection, max_iterations: int) -> None:
    looping = tool_call_message(("get_round_threats", {"round": 1}))
    client = ScriptedClient([looping], repeat_last=True)

    with pytest.raises(AgentError) as caught:
        run_agent(connection, client, 1, 100, max_iterations=max_iterations)

    assert client.call_count == max_iterations
    assert f"No final answer after {max_iterations} iterations" in str(caught.value)


def test_run_agent_default_cap_is_eight(connection: sqlite3.Connection) -> None:
    client = ScriptedClient([tool_call_message(("get_round_threats", {"round": 1}))], True)

    with pytest.raises(AgentError):
        run_agent(connection, client, 1, 100)

    assert client.call_count == 8


def test_run_agent_final_answer_on_last_allowed_iteration(connection: sqlite3.Connection) -> None:
    script = [tool_call_message(("get_round_threats", {"round": 1})), final_message("Done")]
    client = ScriptedClient(script)

    result = run_agent(connection, client, 1, 100, max_iterations=2)

    assert result.answer == "Done"


def test_run_agent_empty_tool_calls_list_is_final(connection: sqlite3.Connection) -> None:
    message = {"role": "assistant", "content": "Done.\nPicks:\n- none", "tool_calls": []}
    client = ScriptedClient([message])

    result = run_agent(connection, client, 1, 100)

    assert result.answer == "Done.\nPicks:\n- none"


def test_dataclasses_are_frozen() -> None:
    pick = Pick("Super Monkey", "0-0-4", 100)
    call = ToolCall("recommend", {}, {})
    result = AgentResult("x", (call,), (pick,))
    for instance in (pick, call, result):
        with pytest.raises(dataclasses.FrozenInstanceError):
            instance.__setattr__(dataclasses.fields(instance)[0].name, "changed")


@pytest.mark.parametrize(
    "fragment",
    ["get_round_threats", "recommend", "Picks:", "- none", "Never state a number"],
)
def test_system_prompt_mentions(fragment: str) -> None:
    assert fragment in SYSTEM_PROMPT


# endregion


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Text\nPicks:\n- Super Monkey 3-0-0 $27000", (Pick("Super Monkey", "3-0-0", 27000),)),
        ("Picks:\n- Super Monkey 0-0-4 $67,855", (Pick("Super Monkey", "0-0-4", 67855),)),
        (
            "Picks:\n- Super Monkey 3-0-0 $27000\n- Dart Monkey 0-2-3 $1,234,567",
            (Pick("Super Monkey", "3-0-0", 27000), Pick("Dart Monkey", "0-2-3", 1234567)),
        ),
        ("Picks:\n- none", ()),
        ("Picks:\n", ()),
        ("No block here, buy a Super Monkey 3-0-0 $27000", ()),
        ("- Super Monkey 3-0-0 $27000", ()),
        ("", ()),
        ("PICKS:\n- Ninja Monkey 1-0-0 $100", (Pick("Ninja Monkey", "1-0-0", 100),)),
        ("picks:\n- Ninja Monkey 1-0-0 $100", (Pick("Ninja Monkey", "1-0-0", 100),)),
        ("  Picks:  \n- Ninja Monkey 1-0-0 $100", (Pick("Ninja Monkey", "1-0-0", 100),)),
        (
            "Picks:\n- Old Tower 0-0-1 $10\nmore text\nPicks:\n- Dart Monkey 0-0-2 $20",
            (Pick("Dart Monkey", "0-0-2", 20),),
        ),
        ("Picks:\n- Old Tower 0-0-1 $10\nPicks:\n- none", ()),
        (
            "Picks:\n- Super Monkey 3-0-0 $27000\nnot a pick line",
            (Pick("Super Monkey", "3-0-0", 27000),),
        ),
        ("Picks:\n- Super Monkey 9-bad $27000", ()),
    ],
    ids=[
        "single",
        "comma_cost",
        "multiple",
        "none",
        "empty_block",
        "no_header",
        "no_header_bullet_only",
        "empty_answer",
        "upper_case_header",
        "lower_case_header",
        "padded_header",
        "last_block_only",
        "last_block_none",
        "trailing_prose",
        "malformed_path",
    ],
)
def test_parse_picks(answer: str, expected: tuple[Pick, ...]) -> None:
    assert parse_picks(answer) == expected


def test_parse_picks_header_must_be_whole_line() -> None:
    assert parse_picks("My Picks: \n- Super Monkey 3-0-0 $27000\nPicks: none") == ()


picks_strategy = st.lists(
    st.builds(
        Pick,
        st.sampled_from(["Super Monkey", "Dart Monkey", "Ninja Monkey"]),
        st.builds("{}-{}-{}".format, *[st.integers(0, 5)] * 3),
        st.integers(0, 10_000_000),
    ),
    max_size=6,
)


@given(picks=picks_strategy)
def test_parse_picks_round_trips(picks: list[Pick]) -> None:
    lines = [f"- {pick.tower_name} {pick.path} ${pick.total_cost:,}" for pick in picks]
    answer = "Reasoning.\nPicks:\n" + "\n".join(lines or ["- none"])

    assert parse_picks(answer) == tuple(picks)


@given(text=st.text(alphabet=st.characters(blacklist_characters="\r"), max_size=200))
def test_parse_picks_is_total(text: str) -> None:
    result = parse_picks(text)

    assert isinstance(result, tuple)
    assert all(isinstance(pick, Pick) for pick in result)


def test_client_from_environment_defaults() -> None:
    client = client_from_environment({API_KEY_VARIABLE: "secret"})

    assert isinstance(client, OpenAICompatibleClient)
    assert DEFAULT_BASE_URL == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert API_KEY_VARIABLE == "GEMINI_API_KEY"
    assert (client.api_key, client.model, client.base_url) == (
        "secret",
        DEFAULT_MODEL,
        DEFAULT_BASE_URL,
    )


def test_client_from_environment_overrides() -> None:
    environ = {
        "GEMINI_API_KEY": "key",
        "BTD6_AGENT_MODEL": "other-model",
        "BTD6_AGENT_BASE_URL": "https://example.test/v1/",
    }

    client = client_from_environment(environ)

    assert (client.model, client.base_url) == ("other-model", "https://example.test/v1/")


@pytest.mark.parametrize("environ", [{}, {"GEMINI_API_KEY": ""}, {"GEMINI_API_KEY": "   "}])
def test_client_from_environment_missing_key(environ: dict[str, str]) -> None:
    with pytest.raises(MissingApiKeyError) as caught:
        client_from_environment(environ)

    assert isinstance(caught.value, AgentError)
    assert "GEMINI_API_KEY" in str(caught.value)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = text
        self.payload = payload or {}

    def json(self) -> dict:
        return self.payload

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(str(self.status_code))


class FakeSession:
    """Replays scripted responses or exceptions; a single item repeats forever."""

    def __init__(self, script: FakeResponse | Exception | list[FakeResponse | Exception]) -> None:
        self.script = script if isinstance(script, list) else [script]
        self.repeat_last = not isinstance(script, list)
        self.calls: list[tuple[str, dict]] = []

    @property
    def response(self) -> FakeResponse | Exception:
        return self.script[0]

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        position = len(self.calls) - 1
        if position >= len(self.script):
            if not self.repeat_last:
                raise AssertionError("FakeSession ran out of scripted items")
            position = len(self.script) - 1
        item = self.script[position]
        if isinstance(item, Exception):
            raise item
        return item


class RecordingSleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def make_client(
    script: FakeResponse | Exception | list[FakeResponse | Exception],
    model: str = "model-x",
) -> tuple[OpenAICompatibleClient, FakeSession, RecordingSleep]:
    session = FakeSession(script)
    sleeper = RecordingSleep()
    client = OpenAICompatibleClient(
        "key", model, "https://host.test/v1/", session=session, sleep=sleeper
    )
    return client, session, sleeper


def ok_response(message: dict) -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": message}]})


def test_complete_posts_openai_request() -> None:
    message = {"role": "assistant", "content": "hi"}
    session = FakeSession(ok_response(message))
    client = OpenAICompatibleClient("key", "model-x", "https://host.test/v1/", session=session)
    messages = [{"role": "user", "content": "hello"}]

    result = client.complete(messages, TOOL_SCHEMAS)

    assert result == message
    url, kwargs = session.calls[0]
    assert url == "https://host.test/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer key"
    assert kwargs["json"] == {"model": "model-x", "messages": messages, "tools": TOOL_SCHEMAS}
    assert kwargs["timeout"] == REQUEST_TIMEOUT_SECONDS


@pytest.mark.parametrize("status", [400, 404, 422])
def test_complete_non_retryable_status_fails_immediately(status: int) -> None:
    client, session, sleeper = make_client(FakeResponse(status, text="boom"))

    with pytest.raises(AgentError) as caught:
        client.complete([], [])

    assert f"HTTP {status}" in str(caught.value)
    assert "boom" in str(caught.value)
    assert len(session.calls) == 1
    assert sleeper.delays == []


@pytest.mark.parametrize("status", [401, 403])
def test_complete_auth_failure_mentions_api_key(status: int) -> None:
    client, session, sleeper = make_client(FakeResponse(status, text="denied"))

    with pytest.raises(AgentError) as caught:
        client.complete([], [])

    assert "API key" in str(caught.value)
    assert "GEMINI_API_KEY" in str(caught.value)
    assert len(session.calls) == 1
    assert sleeper.delays == []


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_complete_retryable_status_exhausts_attempts(status: int) -> None:
    client, session, sleeper = make_client(FakeResponse(status, text="busy"), model="model-y")

    with pytest.raises(AgentError) as caught:
        client.complete([], [])

    assert len(session.calls) == 3
    assert sleeper.delays == [2.0, 5.0]
    message = str(caught.value)
    assert "model-y" in message
    assert f"HTTP {status}" in message
    assert "3 attempts" in message
    assert "BTD6_AGENT_MODEL" in message


def test_retry_constants() -> None:
    assert client_module.RETRY_STATUSES == frozenset({429, 500, 502, 503, 504})
    assert client_module.RETRY_DELAYS_SECONDS == (2.0, 5.0)
    assert DEFAULT_MODEL == "gemini-3.5-flash-lite"
    assert REQUEST_TIMEOUT_SECONDS == 30


def test_complete_success_first_try_does_not_sleep() -> None:
    message = {"role": "assistant", "content": "hi"}
    client, session, sleeper = make_client([ok_response(message)])

    assert client.complete([], []) == message
    assert len(session.calls) == 1
    assert sleeper.delays == []


def test_complete_retries_503_then_succeeds() -> None:
    message = {"role": "assistant", "content": "later"}
    client, session, sleeper = make_client([FakeResponse(503), ok_response(message)])

    assert client.complete([], []) == message
    assert len(session.calls) == 2
    assert sleeper.delays == [2.0]


def test_complete_retries_429_503_then_succeeds() -> None:
    message = {"role": "assistant", "content": "third time"}
    script = [FakeResponse(429), FakeResponse(503), ok_response(message)]
    client, session, sleeper = make_client(script)

    assert client.complete([], []) == message
    assert len(session.calls) == 3
    assert sleeper.delays == [2.0, 5.0]


def test_complete_retries_timeout_then_succeeds() -> None:
    message = {"role": "assistant", "content": "ok"}
    client, session, sleeper = make_client([requests.Timeout("slow"), ok_response(message)])

    assert client.complete([], []) == message
    assert len(session.calls) == 2
    assert sleeper.delays == [2.0]


def test_complete_connection_error_retries_then_raises_agent_error() -> None:
    client, session, sleeper = make_client(requests.ConnectionError("down"), model="model-z")

    with pytest.raises(AgentError) as caught:
        client.complete([], [])

    assert len(session.calls) == 3
    assert sleeper.delays == [2.0, 5.0]
    assert "model-z" in str(caught.value)
    assert "BTD6_AGENT_MODEL" in str(caught.value)


def test_complete_timeout_every_time_names_the_cause() -> None:
    client, _, _ = make_client(requests.Timeout("slow"))

    with pytest.raises(AgentError) as caught:
        client.complete([], [])

    message = str(caught.value).lower()
    assert "timed out" in message or "timeout" in message


def test_complete_other_request_exception_is_agent_error() -> None:
    client, session, sleeper = make_client(requests.exceptions.InvalidURL("bad url"))

    with pytest.raises(AgentError):
        client.complete([], [])

    assert len(session.calls) == 1
    assert sleeper.delays == []


def test_complete_default_sleep_is_time_sleep() -> None:
    client = OpenAICompatibleClient("k", "m", "https://h.test/")

    assert client.sleep is time.sleep


@pytest.mark.parametrize("status", [200, 201, 299])
def test_complete_accepts_2xx(status: int) -> None:
    response = FakeResponse(status, {"choices": [{"message": {"role": "assistant"}}]})
    client = OpenAICompatibleClient("k", "m", "https://h.test/", session=FakeSession(response))

    assert client.complete([], []) == {"role": "assistant"}


def test_complete_creates_default_session() -> None:
    client = OpenAICompatibleClient("k", "m", "https://h.test/")

    assert client.session is not None
