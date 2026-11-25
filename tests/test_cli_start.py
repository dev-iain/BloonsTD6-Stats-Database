from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
import requests
import uvicorn

from btd6 import launcher
from btd6.cli import build_parser, main
from tests.factories import IncomeSetFactory
from tests.test_pipeline import fake_fetch_bloons, fake_fetch_roundset, load_tower_data

pytestmark = pytest.mark.usefixtures("offline_costs_wiki")

STEAM_URI = "steam://rungameid/960090"


@pytest.fixture(autouse=True)
def offline_wiki(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("btd6.cli.fetch_bloons", fake_fetch_bloons)
    monkeypatch.setattr("btd6.cli.fetch_roundset", fake_fetch_roundset)
    monkeypatch.setattr("btd6.cli.fetch_income_set", IncomeSetFactory)
    monkeypatch.setattr("btd6.cli.fetch_tower_module", lambda name: load_tower_data())


@pytest.fixture
def uvicorn_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    return calls


@pytest.fixture
def browser_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, int]]:
    calls: list[tuple[str, str, int]] = []

    def spy(url: str, host: str, port: int) -> None:
        calls.append((url, host, port))

    monkeypatch.setattr(launcher, "open_browser_when_ready", spy)
    return calls


@pytest.fixture
def opened_uris(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    uris: list[str] = []
    monkeypatch.setattr(launcher, "open_uri", uris.append)
    return uris


@pytest.fixture
def existing_db(tmp_path: Path) -> Path:
    database = tmp_path / "btd6.db"
    database.touch()
    return database


def count_upgrades(database_path: Path) -> int:
    connection = sqlite3.connect(database_path)
    try:
        return connection.execute("SELECT COUNT(*) FROM upgrades").fetchone()[0]
    finally:
        connection.close()


def test_parser_knows_start_with_defaults() -> None:
    args = build_parser().parse_args(["start"])
    assert (args.host, args.port, args.refresh, args.no_browser, args.game) == (
        "127.0.0.1",
        8000,
        False,
        False,
        False,
    )


def test_start_all_base(existing_db, uvicorn_calls, browser_calls, opened_uris, capsys):
    code = main(["--db", str(existing_db), "start"])

    assert code == 0
    assert browser_calls == [("http://127.0.0.1:8000", "127.0.0.1", 8000)]
    assert (uvicorn_calls[0]["host"], uvicorn_calls[0]["port"]) == ("127.0.0.1", 8000)
    assert opened_uris == []
    output = capsys.readouterr().out
    assert "Building the database" not in output
    assert "http://127.0.0.1:8000" in output


def test_start_builds_missing_database(tmp_path, uvicorn_calls, browser_calls, capsys):
    database = tmp_path / "new.db"

    code = main(["--db", str(database), "start"])

    output = capsys.readouterr().out
    assert code == 0
    assert "Building the database" in output
    assert "Super Monkey: 64 upgrades" in output
    assert count_upgrades(database) > 0
    assert len(uvicorn_calls) == 1


def test_start_load_failure_removes_new_database(
    tmp_path, monkeypatch, uvicorn_calls, browser_calls, capsys
):
    def unreachable(name: str) -> dict[str, Any]:
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr("btd6.cli.fetch_tower_module", unreachable)
    database = tmp_path / "new.db"

    code = main(["--db", str(database), "start"])

    assert code == 1
    assert not database.exists()
    assert uvicorn_calls == []
    assert browser_calls == []
    assert "Could not reach the wiki" in capsys.readouterr().err


def test_start_refresh_reloads(existing_db, uvicorn_calls, browser_calls, capsys):
    code = main(["--db", str(existing_db), "start", "--refresh"])

    assert code == 0
    assert "Building the database" in capsys.readouterr().out
    assert count_upgrades(existing_db) > 0


def test_start_no_browser(existing_db, uvicorn_calls, browser_calls):
    code = main(["--db", str(existing_db), "start", "--no-browser"])

    assert code == 0
    assert browser_calls == []
    assert len(uvicorn_calls) == 1


def test_start_launches_game(existing_db, uvicorn_calls, browser_calls, opened_uris):
    code = main(["--db", str(existing_db), "start", "--game"])

    assert code == 0
    assert opened_uris == [STEAM_URI]


def test_start_custom_address(existing_db, uvicorn_calls, browser_calls):
    code = main(["--db", str(existing_db), "start", "--host", "0.0.0.0", "--port", "9100"])

    assert code == 0
    assert (uvicorn_calls[0]["host"], uvicorn_calls[0]["port"]) == ("0.0.0.0", 9100)
    assert browser_calls == [("http://127.0.0.1:9100", "0.0.0.0", 9100)]


def test_main_help_lists_start(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "start" in capsys.readouterr().out
