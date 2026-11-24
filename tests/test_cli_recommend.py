from __future__ import annotations

import re
from pathlib import Path

import pytest

from btd6.cli import main
from btd6.db import connect
from btd6.recommend import Recommendation, recommend
from tests.income_fixture import save_connection
from tests.recommend_fixture import build_recommend_database

HEADER_WORDS = ["rank", "tower", "path", "cost", "score", "reasons"]
ROW_PATTERN = re.compile(
    r"^\s*(?P<rank>\d+)\s+(?P<tower>.+?)\s+(?P<path>\d-\d-\d)\s+"
    r"(?P<cost>\S+)\s+(?P<score>\S+)\s+(?P<reasons>.+?)\s*$"
)
NO_RESULT_LINE = "No affordable upgrade can handle this round."
MISSING_ROUNDS_MESSAGE = 'No round data loaded. Run "python -m btd6 load" first.\n'


@pytest.fixture
def db_file(tmp_path: Path) -> str:
    source = build_recommend_database()
    path = save_connection(source, tmp_path / "btd6.db")
    source.close()
    return path


def run_recommend(db_file: str, options: list[str]) -> int:
    return main(["--db", db_file, "recommend", *options])


def base_options(**overrides: str) -> list[str]:
    values = {"--round": "63", "--money": "100000", **overrides}
    return [item for pair in values.items() for item in pair]


def expected_results(db_file: str, *args: object) -> list[Recommendation]:
    connection = connect(db_file)
    try:
        return recommend(connection, *args)
    finally:
        connection.close()


def parse_table(output: str) -> list[dict[str, str]]:
    lines = [line for line in output.splitlines() if line.strip()]
    positions = [lines[0].index(word) for word in HEADER_WORDS]
    assert positions == sorted(positions)
    return [ROW_PATTERN.match(line).groupdict() for line in lines[1:]]


def assert_matches(output: str, expected: list[Recommendation]) -> None:
    rows = parse_table(output)
    assert len(rows) == len(expected)
    for position, (row, result) in enumerate(zip(rows, expected, strict=True), 1):
        assert int(row["rank"]) == position
        assert row["tower"] == result.tower_name
        assert row["path"] == result.path
        assert int(row["cost"]) == result.total_cost
        if result.score is None:
            assert row["score"] == "-"
        else:
            assert float(row["score"]) == pytest.approx(result.score, abs=1e-4)
        assert row["reasons"] == ", ".join(result.reasons)


def test_main_recommend_all_base(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_recommend(db_file, base_options())

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.splitlines()[0].split() == HEADER_WORDS
    rows = parse_table(captured.out)
    assert [row["path"] for row in rows] == ["3-0-0", "0-0-4"]
    assert rows[0]["reasons"] == "affordable, pops_lead, high_pierce"
    assert_matches(captured.out, expected_results(db_file, 63, 100000))


def test_main_recommend_round_not_loaded(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_recommend(db_file, base_options(**{"--round": "150"}))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == "Round 150 is not loaded; loaded rounds are 1-101\n"
    assert captured.out == ""


def test_main_recommend_round_missing(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        run_recommend(db_file, ["--money", "100000"])

    assert caught.value.code == 2
    assert "--round" in capsys.readouterr().err.strip().splitlines()[-1]


def test_main_recommend_round_not_integer(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        run_recommend(db_file, base_options(**{"--round": "abc"}))

    assert caught.value.code == 2
    last_line = capsys.readouterr().err.strip().splitlines()[-1]
    assert last_line == "btd6 recommend: error: argument --round: invalid int value: 'abc'"


def test_main_recommend_nothing_affordable(
    db_file: str, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = run_recommend(db_file, base_options(**{"--money": "100"}))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == NO_RESULT_LINE
    assert captured.err == ""


def test_main_recommend_negative_money(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_recommend(db_file, base_options(**{"--money": "-1"}))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == "money must be 0 or more, got -1\n"
    assert captured.out == ""


def test_main_recommend_money_missing(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        run_recommend(db_file, ["--round", "63"])

    assert caught.value.code == 2
    assert "--money" in capsys.readouterr().err.strip().splitlines()[-1]


def test_main_recommend_hard(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_recommend(db_file, base_options(**{"--difficulty": "hard"}))

    captured = capsys.readouterr()
    expected = expected_results(db_file, 63, 100000, "hard")
    assert exit_code == 0
    assert expected[0].path == "3-0-0"
    assert expected[0].total_cost == 29160
    assert_matches(captured.out, expected)
    assert parse_table(captured.out)[0]["cost"] == "29160"


def test_main_recommend_difficulty_invalid(
    db_file: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as caught:
        run_recommend(db_file, base_options(**{"--difficulty": "nightmare"}))

    assert caught.value.code == 2
    last_line = capsys.readouterr().err.strip().splitlines()[-1]
    assert last_line.startswith(
        "btd6 recommend: error: argument --difficulty: invalid choice: 'nightmare'"
    )


def test_main_recommend_limit_one(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_recommend(db_file, base_options(**{"--limit": "1"}))

    captured = capsys.readouterr()
    rows = parse_table(captured.out)
    assert exit_code == 0
    assert len(rows) == 1
    assert rows[0]["path"] == "3-0-0"
    assert_matches(captured.out, expected_results(db_file, 63, 100000, "medium", 1))


def test_main_recommend_limit_zero(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_recommend(db_file, base_options(**{"--limit": "0"}))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == "limit must be at least 1, got 0\n"
    assert captured.out == ""


def test_main_recommend_database_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_path = tmp_path / "missing.db"

    exit_code = run_recommend(str(missing_path), base_options())

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == (
        f'Database not found at {missing_path}. Run "python -m btd6 load" first.\n'
    )
    assert captured.out == ""
    assert not missing_path.exists()


def test_main_recommend_no_round_data(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = build_recommend_database()
    source.execute("DELETE FROM round_groups")
    source.execute("DELETE FROM rounds")
    source.commit()
    path = save_connection(source, tmp_path / "btd6.db")
    source.close()

    exit_code = run_recommend(path, base_options())

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == MISSING_ROUNDS_MESSAGE
    assert captured.out == ""


def test_main_help_lists_recommend(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--help"])

    assert caught.value.code == 0
    assert "recommend" in capsys.readouterr().out


def test_main_recommend_moab_round(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_recommend(db_file, base_options(**{"--round": "40"}))

    captured = capsys.readouterr()
    rows = parse_table(captured.out)
    assert exit_code == 0
    assert rows[0]["path"] == "0-0-0"
    assert all(row["reasons"].endswith("high_single_target") for row in rows)
    assert_matches(captured.out, expected_results(db_file, 40, 100000))
