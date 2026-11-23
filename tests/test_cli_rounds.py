from __future__ import annotations

from pathlib import Path

import pytest

from btd6.cli import main
from btd6.db import apply_migrations, connect
from btd6.rounds import get_round
from tests.rounds_fixture import build_rounds_db


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = tmp_path / "btd6.db"
    source = build_rounds_db()
    target = connect(str(path))
    source.backup(target)
    target.close()
    return str(path)


def data_lines(out: str) -> list[list[str]]:
    return [line.split() for line in out.strip().splitlines()[1:]]


def run(db_path: str, *args: str) -> int:
    return main(["--db", db_path, "rounds", *args])


def test_main_rounds_single_round(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(db_path, "--round", "1") == 0

    captured = capsys.readouterr()
    rows = data_lines(captured.out)
    assert captured.out.splitlines()[0].split() == [
        "round", "bloon", "count", "camo", "regrow", "fortified", "start", "duration", "rbe",
    ]  # fmt: skip
    assert len(rows) == 1
    assert rows[0][:3] == ["1", "Red", "20"]
    assert captured.err == ""


def test_main_rounds_range(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(db_path, "--from", "1", "--to", "3") == 0

    rows = data_lines(capsys.readouterr().out)
    assert [row[:3] for row in rows] == [
        ["1", "Red", "20"],
        ["2", "Red", "1"],
        ["3", "Red", "5"],
        ["3", "Blue", "3"],
        ["3", "Red", "2"],
    ]


def test_main_rounds_no_selection(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        run(db_path)

    assert excinfo.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == (
        "btd6 rounds: error: one of --round or --from/--to is required"
    )


def test_main_rounds_round_and_range(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        run(db_path, "--round", "1", "--from", "1", "--to", "3")

    assert excinfo.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == (
        "btd6 rounds: error: --round cannot be combined with --from/--to"
    )


def test_main_rounds_from_without_to(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        run(db_path, "--from", "1")

    assert excinfo.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == (
        "btd6 rounds: error: --from and --to must be given together"
    )


def test_main_rounds_zero(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(db_path, "--round", "0") == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert "Round 0 " in captured.err


def test_main_rounds_beyond_loaded_data(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(db_path, "--round", "41") == 2

    assert capsys.readouterr().err.strip() == "Round 41 is not loaded; loaded rounds are 1-40"


def test_main_rounds_non_integer(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        run(db_path, "--round", "abc")

    assert excinfo.value.code == 2
    assert (
        capsys.readouterr()
        .err.splitlines()[-1]
        .startswith("btd6 rounds: error: argument --round: invalid int value: 'abc'")
    )


def test_main_rounds_database_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = str(tmp_path / "missing.db")

    assert run(missing, "--round", "1") == 1

    assert capsys.readouterr().err.strip() == (
        f'Database not found at {missing}. Run "python -m btd6 load" first.'
    )


def test_main_rounds_no_round_data(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = str(tmp_path / "empty.db")
    connection = connect(path)
    apply_migrations(connection)
    connection.close()

    assert run(path, "--round", "1") == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == 'No round data loaded. Run "python -m btd6 load" first.'


def test_main_rounds_reversed_range(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(db_path, "--from", "3", "--to", "1") == 2

    assert capsys.readouterr().err.strip() == "--from must not be greater than --to"


def test_main_rounds_range_of_one_round(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(db_path, "--round", "3")
    single = capsys.readouterr().out
    run(db_path, "--from", "3", "--to", "3")

    assert capsys.readouterr().out == single


def test_main_rounds_range_past_loaded_data(
    db_path: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(db_path, "--from", "39", "--to", "41") == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Round 41 " in captured.err


def test_main_rounds_shows_modifier_flags(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(db_path, "--round", "24")

    row = data_lines(capsys.readouterr().out)[0]
    assert row[3:5] == ["yes", "no"]


def test_main_rounds_help_lists_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["rounds", "--help"])

    out = capsys.readouterr().out
    assert all(flag in out for flag in ("--round", "--from", "--to"))


def test_main_help_lists_rounds_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])

    assert "rounds" in capsys.readouterr().out


def test_main_rounds_matches_query_layer(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(db_path, "--round", "40")

    rows = data_lines(capsys.readouterr().out)
    assert [row[1] for row in rows] == [group.bloon for group in get_round(build_rounds_db(), 40)]
