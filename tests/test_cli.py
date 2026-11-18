from __future__ import annotations

from pathlib import Path

import pytest

from btd6.cli import main


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
