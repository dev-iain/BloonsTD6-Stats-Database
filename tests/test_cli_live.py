from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from btd6 import cli
from btd6.cli import main
from btd6.game_state import fake_game_state, save_game_state
from tests.agent_stub import ScriptedClient, final_message
from tests.income_fixture import save_connection
from tests.recommend_fixture import build_recommend_database

LIVE_LINE = "Live game: round 63, $100,000, difficulty medium"
ANSWER = "Pierce for lead.\nPicks:\n- none"


@pytest.fixture
def db_file(tmp_path: Path) -> str:
    source = build_recommend_database()
    path = save_connection(source, tmp_path / "btd6.db")
    source.close()
    return path


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    return tmp_path / "game_state.json"


def write_state(state_file: Path, difficulty: str = "medium", age_seconds: float = 0) -> None:
    state = fake_game_state(63, 100000, difficulty, [("Super Monkey", "2-0-0")])
    save_game_state(state_file, state, datetime.now(UTC) - timedelta(seconds=age_seconds))


def run(db_file: str, state_file: Path, *argv: str) -> int:
    return main(["--db", db_file, "--state-file", str(state_file), *argv])


def output_of(capsys: pytest.CaptureFixture[str], *argv: str) -> str:
    capsys.readouterr()
    assert main(list(argv)) == 0
    return capsys.readouterr().out


def test_main_recommend_live_all_base(
    db_file: str, state_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_state(state_file)
    expected = output_of(capsys, "--db", db_file, "recommend", "--round", "63", "--money", "100000")

    exit_code = run(db_file, state_file, "recommend", "--live")

    first, _, rest = capsys.readouterr().out.partition("\n")
    assert exit_code == 0
    assert first == LIVE_LINE
    assert rest == expected


def test_main_recommend_live_not_used(
    db_file: str, state_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_state(state_file)

    exit_code = run(db_file, state_file, "recommend", "--round", "63", "--money", "100000")

    assert exit_code == 0
    assert "Live game:" not in capsys.readouterr().out


@pytest.mark.parametrize("extra", [["--round", "5"], ["--money", "10"], ["--difficulty", "hard"]])
def test_main_recommend_live_with_round(
    db_file: str, state_file: Path, capsys: pytest.CaptureFixture[str], extra: list[str]
) -> None:
    write_state(state_file)

    with pytest.raises(SystemExit) as caught:
        run(db_file, state_file, "recommend", "--live", *extra)

    assert caught.value.code == 2
    last_line = capsys.readouterr().err.strip().splitlines()[-1]
    assert last_line.endswith("--live cannot be combined with --round, --money or --difficulty")


@pytest.mark.parametrize("command", ["recommend", "agent"])
def test_main_recommend_live_neither(
    db_file: str, state_file: Path, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    with pytest.raises(SystemExit) as caught:
        run(db_file, state_file, command)

    assert caught.value.code == 2
    last_line = capsys.readouterr().err.strip().splitlines()[-1]
    assert "--round" in last_line and "--money" in last_line


def test_main_recommend_live_stale(
    db_file: str, state_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_state(state_file, age_seconds=3600)

    exit_code = run(db_file, state_file, "recommend", "--live")

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.startswith("Game state is stale")
    assert captured.out == ""


def test_main_recommend_live_missing(
    db_file: str, state_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = run(db_file, state_file, "recommend", "--live")

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.startswith("No game state at")


def test_main_recommend_live_max_age_off(
    db_file: str, state_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_state(state_file, age_seconds=3600)

    exit_code = run(db_file, state_file, "recommend", "--live", "--max-age", "0")

    assert exit_code == 0
    assert capsys.readouterr().out.splitlines()[0] == LIVE_LINE


def test_main_recommend_live_hard(
    db_file: str, state_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_state(state_file, difficulty="hard")
    expected = output_of(
        capsys,
        *("--db", db_file, "recommend", "--round", "63", "--money", "100000"),
        *("--difficulty", "hard"),
    )

    exit_code = run(db_file, state_file, "recommend", "--live")

    first, _, rest = capsys.readouterr().out.partition("\n")
    assert exit_code == 0
    assert first == "Live game: round 63, $100,000, difficulty hard"
    assert rest == expected


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch) -> ScriptedClient:
    client = ScriptedClient([final_message(ANSWER)])
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(cli, "client_from_environment", lambda environ: client)
    return client


def tool_names(client: ScriptedClient) -> list[str]:
    return [tool["function"]["name"] for tool in client.requests[0][1]]


def test_main_agent_live_all_base(db_file: str, state_file: Path, scripted: ScriptedClient) -> None:
    write_state(state_file)

    exit_code = run(db_file, state_file, "agent", "--live")

    assert exit_code == 0
    assert scripted.requests[0][0][1]["content"] == (
        "Round 63, money $100000, difficulty medium. You own: Super Monkey 2-0-0. "
        "Recommend what to buy."
    )
    assert "get_game_state" in tool_names(scripted)


def test_main_agent_live_not_used(db_file: str, state_file: Path, scripted: ScriptedClient) -> None:
    write_state(state_file)

    exit_code = run(db_file, state_file, "agent", "--round", "63", "--money", "100000")

    assert exit_code == 0
    assert "get_game_state" not in tool_names(scripted)


def test_main_agent_live_with_round(
    db_file: str, state_file: Path, scripted: ScriptedClient
) -> None:
    write_state(state_file)

    with pytest.raises(SystemExit) as caught:
        run(db_file, state_file, "agent", "--live", "--round", "63")

    assert caught.value.code == 2


def test_main_agent_live_missing(
    db_file: str,
    state_file: Path,
    scripted: ScriptedClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = run(db_file, state_file, "agent", "--live")

    assert exit_code == 1
    assert capsys.readouterr().err.startswith("No game state at")
    assert scripted.call_count == 0
