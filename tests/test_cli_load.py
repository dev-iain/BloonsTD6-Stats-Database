from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import requests

from btd6.cli import main
from tests.test_pipeline import load_tower_data

ALL_LINES = (
    "Super Monkey: 64 upgrades\n"
    "Wizard Monkey: 64 upgrades\n"
    "Ninja Monkey: 64 upgrades\n"
    "Alchemist: 64 upgrades\n"
    "Druid: 64 upgrades\n"
)
LINES_WITHOUT_ALCHEMIST = (
    "Super Monkey: 64 upgrades\n"
    "Wizard Monkey: 64 upgrades\n"
    "Ninja Monkey: 64 upgrades\n"
    "Druid: 64 upgrades\n"
)


def succeeding_fetch(tower_name: str) -> dict[str, Any]:
    return load_tower_data()


def bad_alchemist_fetch(tower_name: str) -> dict[str, Any]:
    if tower_name == "Alchemist":
        raise ValueError("no upgrade data")
    return load_tower_data()


def unreachable_fetch(tower_name: str) -> dict[str, Any]:
    raise requests.ConnectionError("connection refused")


def install_fetch(monkeypatch: pytest.MonkeyPatch, fake: Callable[[str], dict[str, Any]]) -> None:
    monkeypatch.setattr("btd6.cli.fetch_tower_module", fake)


def count_upgrades(database_path: Path) -> int:
    connection = sqlite3.connect(database_path)
    try:
        return connection.execute("SELECT COUNT(*) FROM upgrades").fetchone()[0]
    finally:
        connection.close()


@pytest.fixture
def new_db(tmp_path: Path) -> Path:
    return tmp_path / "new.db"


def test_main_load_all_base(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, succeeding_fetch)

    exit_code = main(["--db", str(new_db), "load"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ALL_LINES
    assert captured.err == ""
    assert new_db.exists()
    assert count_upgrades(new_db) == 320


def test_main_load_one_tower(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, succeeding_fetch)

    exit_code = main(["--db", str(new_db), "load", "--tower", "Wizard Monkey"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "Wizard Monkey: 64 upgrades\n"
    assert captured.err == ""
    assert count_upgrades(new_db) == 64


def test_main_load_not_a_magic_tower(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, succeeding_fetch)

    with pytest.raises(SystemExit) as exit_info:
        main(["--db", str(new_db), "load", "--tower", "Dart Monkey"])

    captured = capsys.readouterr()
    assert exit_info.value.code == 2
    last_line = captured.err.strip().splitlines()[-1]
    assert last_line.startswith("btd6 load: error: argument --tower: invalid choice: 'Dart Monkey'")
    assert not new_db.exists()


def test_main_load_one_tower_bad_data(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, bad_alchemist_fetch)

    exit_code = main(["--db", str(new_db), "load"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == LINES_WITHOUT_ALCHEMIST
    assert captured.err == "Alchemist: failed: no upgrade data\n"
    assert count_upgrades(new_db) == 256


def test_main_load_wiki_unreachable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, unreachable_fetch)

    exit_code = main(["--db", str(new_db), "load"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == "Could not reach the wiki: connection refused\n"
    assert captured.out == ""


def test_main_load_already_loaded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, succeeding_fetch)
    main(["--db", str(new_db), "load"])
    capsys.readouterr()

    exit_code = main(["--db", str(new_db), "load"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ALL_LINES
    assert captured.err == ""
    assert count_upgrades(new_db) == 320
