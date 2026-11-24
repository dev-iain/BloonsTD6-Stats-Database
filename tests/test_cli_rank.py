from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from btd6.cli import main
from btd6.db import connect
from btd6.db.loader import load_tower
from btd6.query import UpgradeFilters
from btd6.ranking import rank_upgrades
from tests.test_ranking import UPGRADE_STATS, build_database

NO_MATCH_LINE = "No upgrades match these filters."
HEADER_WORDS = ["rank", "tower", "path", "cost", "DPS", "MOAB DPS", "damage per dollar"]
ROW_PATTERN = re.compile(
    r"^\s*(?P<rank>\d+)\s+(?P<tower>.+?)\s+(?P<path>\d-\d-\d)\s+"
    r"(?P<cost>\S+)\s+(?P<dps>\S+)\s+(?P<moab_dps>\S+)\s+(?P<per_dollar>\S+)\s*$"
)
METRIC_NAMES = {
    "dps": "dps",
    "dollar": "damage_per_dollar",
    "pierce-dollar": "pierce_damage_per_dollar",
    "moab-dps": "moab_dps",
}
DIFFICULTIES = ["easy", "medium", "hard", "impoppable"]


@pytest.fixture
def db_file(tmp_path: Path) -> str:
    path = tmp_path / "btd6.db"
    memory = build_database(UPGRADE_STATS)
    disk = connect(str(path))
    memory.backup(disk)
    disk.close()
    memory.close()
    return str(path)


def expected_frame(
    db_file: str, filters: UpgradeFilters | None = None, **kwargs: Any
) -> pandas.DataFrame:
    connection = connect(db_file)
    try:
        return rank_upgrades(connection, filters or UpgradeFilters(), **kwargs)
    finally:
        connection.close()


def parse_table(output: str) -> list[dict[str, str]]:
    lines = [line for line in output.splitlines() if line.strip()]
    positions = [lines[0].index(word) for word in HEADER_WORDS]
    assert positions == sorted(positions)
    return [ROW_PATTERN.match(line).groupdict() for line in lines[1:]]


def assert_matches(output: str, frame: pandas.DataFrame) -> None:
    rows = parse_table(output)
    assert len(rows) == len(frame)
    expected_rows = frame.to_dict("records")
    for position, (row, expected) in enumerate(zip(rows, expected_rows, strict=True), 1):
        assert int(row["rank"]) == position
        assert row["tower"] == expected["tower_name"]
        assert row["path"] == expected["path"]
        assert float(row["cost"]) == pytest.approx(expected["total_cost"], rel=1e-2)
        assert float(row["dps"]) == pytest.approx(expected["dps"], rel=1e-2)
        assert float(row["moab_dps"]) == pytest.approx(expected["moab_dps"], rel=1e-2)


def run_rank(db_file: str, options: list[str]) -> int:
    return main(["--db", db_file, "rank", *options])


def test_main_rank_all_base(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_rank(db_file, [])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert_matches(captured.out, expected_frame(db_file, metric="damage_per_dollar"))


@pytest.mark.parametrize("flag_value", list(METRIC_NAMES))
def test_main_rank_metric_choices(
    db_file: str, capsys: pytest.CaptureFixture[str], flag_value: str
) -> None:
    exit_code = run_rank(db_file, ["--metric", flag_value])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert_matches(captured.out, expected_frame(db_file, metric=METRIC_NAMES[flag_value]))


def test_main_rank_metric_invalid(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        run_rank(db_file, ["--metric", "bogus"])

    assert caught.value.code == 2
    last_line = capsys.readouterr().err.splitlines()[-1]
    assert last_line.startswith("btd6 rank: error: argument --metric: invalid choice: 'bogus'")


def test_main_rank_metric_rejects_query_layer_spelling(db_file: str) -> None:
    with pytest.raises(SystemExit) as caught:
        run_rank(db_file, ["--metric", "damage_per_dollar"])
    assert caught.value.code == 2


@pytest.mark.parametrize("difficulty", DIFFICULTIES)
def test_main_rank_difficulty_choices(
    db_file: str, capsys: pytest.CaptureFixture[str], difficulty: str
) -> None:
    exit_code = run_rank(db_file, ["--difficulty", difficulty])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert_matches(captured.out, expected_frame(db_file, difficulty=difficulty))


def test_main_rank_difficulty_invalid(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        run_rank(db_file, ["--difficulty", "nightmare"])

    assert caught.value.code == 2
    last_line = capsys.readouterr().err.splitlines()[-1]
    assert last_line.startswith(
        "btd6 rank: error: argument --difficulty: invalid choice: 'nightmare'"
    )


def test_main_rank_limit_one(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_rank(db_file, ["--limit", "1"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert_matches(captured.out, expected_frame(db_file, limit=1))
    assert len(parse_table(captured.out)) == 1


def test_main_rank_limit_zero(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_rank(db_file, ["--limit", "0"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == "limit must be at least 1, got 0\n"
    assert captured.out == ""


def test_main_rank_limit_not_an_integer(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        run_rank(db_file, ["--limit", "abc"])

    assert caught.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == (
        "btd6 rank: error: argument --limit: invalid int value: 'abc'"
    )


def test_main_rank_can_pop_lead(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_rank(db_file, ["--can-pop", "lead"])

    captured = capsys.readouterr()
    filters = UpgradeFilters(can_pop_lead=True)
    assert exit_code == 0
    assert_matches(captured.out, expected_frame(db_file, filters))


def test_main_rank_tower_option_selects_military_tower(
    db_file: str, super_monkey_resolved: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    connection = connect(db_file)
    load_tower(connection, "Sniper Monkey", super_monkey_resolved, "Military")
    connection.close()

    exit_code = run_rank(db_file, ["--tower", "Sniper Monkey"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Sniper Monkey" in captured.out
    assert "Super Monkey" not in captured.out


def test_main_rank_no_match(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_rank(db_file, ["--min-pierce", "99"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.strip() == NO_MATCH_LINE


def test_main_rank_lead_in_both_flags(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_rank(db_file, ["--can-pop", "lead", "--cannot-pop", "lead"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == "--can-pop and --cannot-pop both list lead\n"
    assert captured.out == ""


def test_main_rank_database_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing_path = tmp_path / "missing.db"

    exit_code = run_rank(str(missing_path), [])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == (
        f'Database not found at {missing_path}. Run "python -m btd6 load" first.\n'
    )
    assert captured.out == ""
    assert not missing_path.exists()


def test_main_rank_defaults_match_explicit(
    db_file: str, capsys: pytest.CaptureFixture[str]
) -> None:
    run_rank(db_file, [])
    default_output = capsys.readouterr().out
    run_rank(db_file, ["--metric", "dollar", "--difficulty", "medium"])
    explicit_output = capsys.readouterr().out

    assert default_output
    assert default_output == explicit_output


def test_main_rank_difficulty_changes_cost(
    db_file: str, capsys: pytest.CaptureFixture[str]
) -> None:
    run_rank(db_file, ["--difficulty", "easy"])
    easy = {row["path"]: float(row["cost"]) for row in parse_table(capsys.readouterr().out)}
    run_rank(db_file, ["--difficulty", "hard"])
    hard = {row["path"]: float(row["cost"]) for row in parse_table(capsys.readouterr().out)}

    assert hard["0-0-0"] > easy["0-0-0"]


def test_main_rank_ranks_are_sequential(db_file: str, capsys: pytest.CaptureFixture[str]) -> None:
    run_rank(db_file, [])

    ranks = [int(row["rank"]) for row in parse_table(capsys.readouterr().out)]
    assert ranks == list(range(1, len(UPGRADE_STATS) + 1))


def test_main_help_lists_rank(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--help"])

    assert caught.value.code == 0
    assert "rank" in capsys.readouterr().out


@settings(max_examples=25, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    metric=st.sampled_from(list(METRIC_NAMES)),
    difficulty=st.sampled_from(DIFFICULTIES),
    limit=st.one_of(st.none(), st.integers(min_value=1, max_value=6)),
)
def test_main_rank_matches_rank_upgrades_property(
    db_file: str,
    capsys: pytest.CaptureFixture[str],
    metric: str,
    difficulty: str,
    limit: int | None,
) -> None:
    options = ["--metric", metric, "--difficulty", difficulty]
    if limit is not None:
        options += ["--limit", str(limit)]

    exit_code = run_rank(db_file, options)

    captured = capsys.readouterr()
    frame = expected_frame(db_file, metric=METRIC_NAMES[metric], difficulty=difficulty, limit=limit)
    assert exit_code == 0
    assert_matches(captured.out, frame)


def test_main_rank_warns_when_attacks_not_loaded(
    db_file: str, capsys: pytest.CaptureFixture[str]
) -> None:
    connection = connect(db_file)
    connection.execute("DELETE FROM attacks")
    connection.commit()
    connection.close()

    exit_code = run_rank(db_file, [])

    assert exit_code == 0
    assert 'Run "python -m btd6 load"' in capsys.readouterr().err
