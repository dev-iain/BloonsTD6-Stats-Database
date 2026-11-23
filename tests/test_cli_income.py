from __future__ import annotations

import contextlib
import io
import sqlite3
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.cli import main
from btd6.db import apply_migrations, connect
from btd6.income import cumulative_income, round_income
from tests.income_fixture import build_connection, save_connection

LAST_ROUND = 100
TABLE_HEADER = ["round", "pop", "cash", "end", "bonus", "total", "running", "total"]
NOT_LOADED = "Round {number} is not loaded; loaded rounds are 1-{last}"


@pytest.fixture(scope="module")
def db_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    return save_connection(build_connection(LAST_ROUND), tmp_path_factory.mktemp("income") / "a.db")


def run(db_path: str, *args: str) -> int:
    return main(["--db", db_path, "income", *args])


def data_rows(out: str) -> list[list[str]]:
    return [line.split() for line in out.strip().splitlines()[1:]]


def run_capturing(db_path: str, *args: str) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = run(db_path, *args)
    return code, buffer.getvalue()


def test_main_income_round_one(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(db_path, "--round", "1") == 0

    captured = capsys.readouterr()
    assert captured.out == "Round 1: $20 pop cash + $101 end bonus = $121\n"
    assert captured.err == ""


@pytest.mark.parametrize("round_number", [40, 63, 80, 100])
def test_main_income_round_prints_income_summary(
    db_path: str, capsys: pytest.CaptureFixture[str], round_number: int
) -> None:
    from btd6.formatting import income_summary

    assert run(db_path, "--round", str(round_number)) == 0

    expected = income_summary(round_income(sqlite3.connect(db_path), round_number), round_number)
    assert capsys.readouterr().out == expected + "\n"


def test_main_income_round_fractional(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(db_path, "--round", "80")

    assert capsys.readouterr().out == "Round 80: $1,220.2 pop cash + $180 end bonus = $1,400.2\n"


def test_main_income_up_to_one(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(db_path, "--up-to", "1") == 0

    out = capsys.readouterr().out
    assert out.splitlines()[0].split() == TABLE_HEADER
    assert data_rows(out) == [["1", "20", "101", "121", "121"]]


def test_main_income_up_to_five(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(db_path, "--up-to", "5")

    assert data_rows(capsys.readouterr().out) == [
        ["1", "20", "101", "121", "121"],
        ["2", "35", "102", "137", "258"],
        ["3", "35", "103", "138", "396"],
        ["4", "71", "104", "175", "571"],
        ["5", "59", "105", "164", "735"],
    ]


def test_main_income_up_to_forty(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(db_path, "--up-to", "40")

    rows = data_rows(capsys.readouterr().out)
    assert len(rows) == 40
    assert rows[-1] == ["40", "381", "140", "521", "16856"]


def test_main_income_up_to_fractional_cells(
    db_path: str, capsys: pytest.CaptureFixture[str]
) -> None:
    run(db_path, "--up-to", "80")

    assert data_rows(capsys.readouterr().out)[-1][:4] == ["80", "1220.2", "180", "1400.2"]


def test_main_income_up_to_last_round(db_path: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(db_path, "--up-to", "100")

    rows = data_rows(capsys.readouterr().out)
    assert len(rows) == LAST_ROUND
    assert float(rows[-1][4]) == pytest.approx(178994.4)


def test_main_income_up_to_row_agrees_with_round(
    db_path: str, capsys: pytest.CaptureFixture[str]
) -> None:
    run(db_path, "--up-to", "63")
    table_row = data_rows(capsys.readouterr().out)[-1]
    run(db_path, "--round", "63")
    summary = capsys.readouterr().out

    assert table_row[:4] == ["63", "2663", "163", "2826"]
    assert "$2,663 pop cash" in summary
    assert "$2,826" in summary


@settings(max_examples=25, deadline=None)
@given(up_to=st.integers(min_value=1, max_value=LAST_ROUND))
def test_main_income_up_to_matches_income_functions(db_path: str, up_to: int) -> None:
    code, out = run_capturing(db_path, "--up-to", str(up_to))
    rows = data_rows(out)

    assert code == 0
    assert [row[0] for row in rows] == [str(number) for number in range(1, up_to + 1)]
    expected = cumulative_income(sqlite3.connect(db_path), up_to)
    assert float(rows[-1][4]) == pytest.approx(expected, abs=0.1)
    running = [float(row[4]) for row in rows]
    assert running == sorted(running)
    assert all(
        float(row[3]) == pytest.approx(float(row[1]) + float(row[2]), abs=0.1) for row in rows
    )


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "btd6 income: error: one of the arguments --round --up-to is required"),
        (
            ["--round", "1", "--up-to", "5"],
            "btd6 income: error: argument --up-to: not allowed with argument --round",
        ),
        (["--round", "abc"], "btd6 income: error: argument --round: invalid int value: 'abc'"),
        (["--up-to", "x"], "btd6 income: error: argument --up-to: invalid int value: 'x'"),
    ],
)
def test_main_income_argparse_errors(
    db_path: str, capsys: pytest.CaptureFixture[str], args: list[str], message: str
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        run(db_path, *args)

    assert excinfo.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == message


@pytest.mark.parametrize(
    ("flag", "value"),
    [("--round", "0"), ("--round", "101"), ("--round", "-1"), ("--up-to", "0"), ("--up-to", "101")],
)
def test_main_income_out_of_range(
    db_path: str, capsys: pytest.CaptureFixture[str], flag: str, value: str
) -> None:
    assert run(db_path, flag, value) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == NOT_LOADED.format(number=value, last=LAST_ROUND)


def test_main_income_database_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = str(tmp_path / "missing.db")

    assert run(missing, "--round", "1") == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == (
        f'Database not found at {missing}. Run "python -m btd6 load" first.'
    )
    assert not Path(missing).exists()


@pytest.mark.parametrize("args", [("--round", "1"), ("--up-to", "5")])
def test_main_income_no_round_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], args: tuple[str, ...]
) -> None:
    path = str(tmp_path / "empty.db")
    connection = connect(path)
    apply_migrations(connection)
    connection.close()

    assert run(path, *args) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == 'No round data loaded. Run "python -m btd6 load" first.'


@pytest.mark.parametrize("args", [("--round", "1"), ("--up-to", "5")])
def test_main_income_no_income_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], args: tuple[str, ...]
) -> None:
    path = save_connection(build_connection(5, with_income=False), tmp_path / "noincome.db")

    assert run(path, *args) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert "income" in captured.err.lower()
    assert 'Run "python -m btd6 load" first.' in captured.err


def test_main_income_short_database_bounds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = save_connection(build_connection(5), tmp_path / "short.db")

    assert run(path, "--up-to", "6") == 2
    assert capsys.readouterr().err.strip() == NOT_LOADED.format(number=6, last=5)


def test_main_income_help_lists_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["income", "--help"])

    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert all(flag in out for flag in ("--round", "--up-to"))


def test_main_help_lists_income_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])

    assert "income" in capsys.readouterr().out
