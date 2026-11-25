from __future__ import annotations

from pathlib import Path

import pytest

from btd6 import cli
from btd6.agent.client import AgentError
from btd6.cli import main
from tests.agent_stub import ScriptedClient, final_message, tool_call_message
from tests.income_fixture import save_connection
from tests.recommend_fixture import build_recommend_database

ANSWER = "Pierce for lead.\nPicks:\n- Super Monkey 3-0-0 $27,000"
MISSING_KEY_MESSAGE = (
    "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey "
    "and paste it into gemini_api_key.txt in the project folder (or export GEMINI_API_KEY).\n"
)


@pytest.fixture
def db_file(tmp_path: Path) -> str:
    source = build_recommend_database()
    path = save_connection(source, tmp_path / "btd6.db")
    source.close()
    return path


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch) -> ScriptedClient:
    client = ScriptedClient(
        [tool_call_message(("get_round_threats", {"round": 63})), final_message(ANSWER)]
    )
    patch_client(monkeypatch, client)
    return client


def patch_client(monkeypatch: pytest.MonkeyPatch, client: object) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(cli, "client_from_environment", lambda *args: client)


def run_agent_cli(db_file: str, *options: str) -> int:
    return main(["--db", db_file, "agent", "--round", "63", "--money", "5000", *options])


def test_main_agent_prints_answer(
    db_file: str, scripted: ScriptedClient, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = run_agent_cli(db_file)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert ANSWER in captured.out
    assert captured.err == ""
    assert scripted.call_count == 2
    assert "Round 63, money $5000, difficulty medium" in scripted.requests[0][0][1]["content"]


def test_main_agent_missing_api_key(
    db_file: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cli, "API_KEY_FILES", (tmp_path / "no.env", tmp_path / "no.txt"))

    exit_code = run_agent_cli(db_file)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "GEMINI_API_KEY" in captured.err
    assert captured.err == MISSING_KEY_MESSAGE
    assert captured.out == ""


def test_main_agent_blank_api_key(
    db_file: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "  ")
    monkeypatch.setattr(cli, "API_KEY_FILES", (tmp_path / "no.env", tmp_path / "no.txt"))

    exit_code = run_agent_cli(db_file)

    assert exit_code == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard", "impoppable"])
def test_main_agent_difficulty_choices(
    db_file: str, scripted: ScriptedClient, difficulty: str
) -> None:
    exit_code = run_agent_cli(db_file, "--difficulty", difficulty)

    assert exit_code == 0
    assert f"difficulty {difficulty}." in scripted.requests[0][0][1]["content"]


def test_main_agent_difficulty_invalid(
    db_file: str, scripted: ScriptedClient, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as caught:
        run_agent_cli(db_file, "--difficulty", "nightmare")

    assert caught.value.code == 2
    last_line = capsys.readouterr().err.strip().splitlines()[-1]
    assert last_line.startswith(
        "btd6 agent: error: argument --difficulty: invalid choice: 'nightmare'"
    )


def test_main_agent_max_iterations_option(
    db_file: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    looping = ScriptedClient([tool_call_message(("get_round_threats", {"round": 63}))], True)
    patch_client(monkeypatch, looping)

    exit_code = run_agent_cli(db_file, "--max-iterations", "3")

    captured = capsys.readouterr()
    assert exit_code == 1
    assert looping.call_count == 3
    assert "No final answer after 3 iterations" in captured.err
    assert captured.out == ""


def test_main_agent_max_iterations_not_integer(db_file: str, scripted: ScriptedClient) -> None:
    with pytest.raises(SystemExit) as caught:
        run_agent_cli(db_file, "--max-iterations", "many")

    assert caught.value.code == 2


@pytest.mark.parametrize("missing", ["--round", "--money"])
def test_main_agent_required_options(db_file: str, scripted: ScriptedClient, missing: str) -> None:
    options = {"--round": "63", "--money": "5000"}
    del options[missing]
    argv = [item for pair in options.items() for item in pair]

    with pytest.raises(SystemExit) as caught:
        main(["--db", db_file, "agent", *argv])

    assert caught.value.code == 2


def test_main_agent_agent_error_from_client(
    db_file: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FailingClient:
        def complete(self, messages: list[dict], tools: list[dict]) -> dict:
            raise AgentError("HTTP 429 from provider")

    patch_client(monkeypatch, FailingClient())

    exit_code = run_agent_cli(db_file)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "HTTP 429 from provider" in captured.err
    assert captured.out == ""


def test_main_agent_database_missing(
    tmp_path: Path, scripted: ScriptedClient, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_path = tmp_path / "missing.db"

    exit_code = run_agent_cli(str(missing_path))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == (
        f'Database not found at {missing_path}. Run "python -m btd6 load" first.\n'
    )
    assert scripted.call_count == 0
    assert not missing_path.exists()


def test_main_agent_busy_model_error_is_a_clean_message(
    db_file: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class BusyClient:
        def complete(self, messages: list[dict], tools: list[dict]) -> dict:
            raise AgentError(
                "gemini-3.8-flash is busy or unreachable (HTTP 503) after 3 attempts. "
                "Try again in a minute, or set BTD6_AGENT_MODEL to another model."
            )

    patch_client(monkeypatch, BusyClient())

    exit_code = run_agent_cli(db_file)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "BTD6_AGENT_MODEL" in captured.err
    assert "Unexpected error" not in captured.err
    assert captured.out == ""


def test_main_agent_key_from_txt_file(
    db_file: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    key_file = tmp_path / "gemini_api_key.txt"
    key_file.write_text("# paste below\nfile-key\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cli, "API_KEY_FILES", (tmp_path / "no.env", key_file))
    scripted_client = ScriptedClient([final_message(ANSWER)])
    built_keys: list[str] = []

    def build_client(api_key: str, model: str, base_url: str) -> ScriptedClient:
        built_keys.append(api_key)
        return scripted_client

    monkeypatch.setattr("btd6.agent.client.OpenAICompatibleClient", build_client)

    exit_code = run_agent_cli(db_file)

    assert exit_code == 0
    assert built_keys == ["file-key"]
    assert ANSWER in capsys.readouterr().out
