from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import requests

from btd6.cli import main
from tests.test_pipeline import (
    fake_fetch_bloons,
    fake_fetch_roundset,
    load_tower_data,
    raising,
)

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

ROUNDS_LINE = "Rounds: 3 rounds, 5 groups\n"

pytestmark = pytest.mark.usefixtures("offline_costs_wiki")


@pytest.fixture(autouse=True)
def offline_rounds_wiki(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("btd6.cli.fetch_bloons", fake_fetch_bloons)
    monkeypatch.setattr("btd6.cli.fetch_roundset", fake_fetch_roundset)


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
    assert captured.out == ALL_LINES + ROUNDS_LINE
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
    assert captured.out == "Wizard Monkey: 64 upgrades\n" + ROUNDS_LINE
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
    assert captured.out == LINES_WITHOUT_ALCHEMIST + ROUNDS_LINE
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
    assert captured.out == ALL_LINES + ROUNDS_LINE
    assert captured.err == ""
    assert count_upgrades(new_db) == 320


def count_table(database_path: Path, table: str) -> int:
    connection = sqlite3.connect(database_path)
    try:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        connection.close()


def test_main_load_rounds_base(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, succeeding_fetch)

    exit_code = main(["--db", str(new_db), "load"])

    assert exit_code == 0
    assert capsys.readouterr().out.splitlines()[-1] == "Rounds: 3 rounds, 5 groups"
    assert count_table(new_db, "rounds") == 3
    assert count_table(new_db, "round_groups") == 5
    assert count_table(new_db, "bloons") == 3


def test_main_load_no_rounds_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, succeeding_fetch)
    monkeypatch.setattr("btd6.cli.fetch_bloons", raising(AssertionError("bloons fetched")))
    monkeypatch.setattr("btd6.cli.fetch_roundset", raising(AssertionError("rounds fetched")))

    exit_code = main(["--db", str(new_db), "load", "--no-rounds"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ALL_LINES
    assert "Rounds:" not in captured.out
    for table in ("rounds", "round_groups", "bloons"):
        assert count_table(new_db, table) == 0


def test_main_load_bloons_fetch_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, succeeding_fetch)
    error = ValueError("Wiki cargo query returned no rows")
    monkeypatch.setattr("btd6.cli.fetch_bloons", raising(error))

    exit_code = main(["--db", str(new_db), "load"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == "Bloons: failed: Wiki cargo query returned no rows\n"
    assert "Rounds:" not in captured.out
    assert count_upgrades(new_db) == 320
    assert count_table(new_db, "rounds") == 0


def test_main_load_roundset_fetch_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, succeeding_fetch)
    error = ValueError('Roundset "DefaultRoundSet" not found on the wiki')
    monkeypatch.setattr("btd6.cli.fetch_roundset", raising(error))

    exit_code = main(["--db", str(new_db), "load"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == 'Rounds: failed: Roundset "DefaultRoundSet" not found on the wiki\n'
    assert count_upgrades(new_db) == 320
    assert count_table(new_db, "bloons") == 3
    assert count_table(new_db, "round_groups") == 0


def test_main_load_rounds_already_loaded(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, succeeding_fetch)
    main(["--db", str(new_db), "load"])
    first_output = capsys.readouterr().out

    exit_code = main(["--db", str(new_db), "load"])

    assert exit_code == 0
    assert capsys.readouterr().out == first_output
    assert count_table(new_db, "rounds") == 3
    assert count_table(new_db, "round_groups") == 5
    assert count_table(new_db, "bloons") == 3
    assert count_upgrades(new_db) == 320


def test_main_load_no_rounds_keeps_existing_rounds(monkeypatch: pytest.MonkeyPatch, new_db: Path):
    install_fetch(monkeypatch, succeeding_fetch)
    main(["--db", str(new_db), "load"])

    exit_code = main(["--db", str(new_db), "load", "--no-rounds"])

    assert exit_code == 0
    assert count_table(new_db, "round_groups") == 5


def test_main_load_no_rounds_with_tower(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new_db: Path
):
    install_fetch(monkeypatch, succeeding_fetch)

    exit_code = main(["--db", str(new_db), "load", "--no-rounds", "--tower", "Wizard Monkey"])

    assert exit_code == 0
    assert capsys.readouterr().out == "Wizard Monkey: 64 upgrades\n"
    assert count_upgrades(new_db) == 64
    assert count_table(new_db, "rounds") == 0
