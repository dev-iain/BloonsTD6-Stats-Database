from __future__ import annotations

import re
from pathlib import Path

import pytest

from btd6.cli import HANDLERS, build_parser, main
from btd6.etl.fetch import PROJECT_ROOT


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "btd6.db")


def test_main_search_load_given_search_options(
    db_path: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--db", db_path, "load", "--cannot-pop", "lead", "--min-pierce", "1"]

    with pytest.raises(SystemExit) as excinfo:
        main(argv)

    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert captured.err.splitlines()[-1] == (
        "btd6: error: unrecognized arguments: --cannot-pop lead --min-pierce 1"
    )


def test_main_search_no_command(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--db", db_path])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err.startswith("usage: btd6")
    assert captured.out == ""


def test_main_search_unknown_command(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--db", db_path, "fetch"])

    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert captured.err.splitlines()[-1].startswith(
        "btd6: error: argument command: invalid choice: 'fetch'"
    )


def test_main_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])

    captured = capsys.readouterr()
    assert excinfo.value.code == 0
    assert "load" in captured.out
    assert "search" in captured.out


def test_build_parser_db_default():
    args = build_parser().parse_args(["search"])
    assert args.db == str(PROJECT_ROOT / "btd6.db")


def test_build_parser_db_override():
    args = build_parser().parse_args(["--db", "custom.db", "load"])
    assert args.db == "custom.db"


@pytest.mark.parametrize("command", ["search", "load"])
def test_build_parser_subcommand(command):
    assert build_parser().parse_args([command]).command == command


@pytest.mark.parametrize(
    "expected",
    [
        "SQLite database path",
        "load resolved tower data into the database",
        "search towers and upgrades by stats",
    ],
)
def test_format_help_texts(expected):
    pattern = rf"(?<!\S){re.escape(expected)}(?!\S)"
    assert re.search(pattern, build_parser().format_help())


@pytest.mark.parametrize("command", ["load", "search"])
def test_main_stub_command_not_implemented_retire_when_43_45_land(
    command, capsys: pytest.CaptureFixture[str]
):
    exit_code = main([command])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == f"{command}: not implemented\n"
    assert captured.out == ""


def test_main_dispatches_parsed_namespace_to_handler(db_path: str, monkeypatch):
    received = []

    def spy(args):
        received.append(args)
        return 7

    monkeypatch.setitem(HANDLERS, "search", spy)

    assert main(["--db", db_path, "search"]) == 7
    assert len(received) == 1
    assert received[0].command == "search"
    assert received[0].db == db_path
