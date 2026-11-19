from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from btd6.cli import format_results, main
from btd6.db import connect
from btd6.query import search_upgrades
from tests.test_query import (
    build_database,
    insert_tower,
    insert_upgrade,
    load_all_rows,
)

NO_MATCH_OUTPUT = "No upgrades match these filters.\n"
BASE_OPTIONS = ["--cannot-pop", "lead", "--min-pierce", "1"]
ALL_PATHS = ["0-0-0", "1-1-0", "2-0-0", "2-1-0"]


def build_database_file(
    path: Path, csv_path: Path, with_rows: bool = True, with_dart_monkey: bool = False
) -> str:
    connection = build_database(csv_path, with_rows=with_rows, path=str(path))
    if with_dart_monkey:
        add_dart_monkey(connection, csv_path)
    connection.commit()
    connection.close()
    return str(path)


def add_dart_monkey(connection: sqlite3.Connection, csv_path: Path) -> None:
    tower_id = insert_tower(connection, "Dart Monkey", "Primary")
    insert_upgrade(
        connection,
        tower_id,
        load_all_rows(csv_path)["0-0-0"],
        damage_type="Sharp",
        can_hit_camo=False,
        stat_overrides={"projectile_pierce": 3.0},
    )


@pytest.fixture
def db_file(tmp_path: Path, golden_csv_path: Path) -> str:
    return build_database_file(tmp_path / "btd6.db", golden_csv_path)


@pytest.fixture
def expected_table(db_file: str):
    def render(paths: list[str]) -> str:
        connection = connect(db_file)
        try:
            by_path = {row["path"]: row for row in search_upgrades(connection)}
        finally:
            connection.close()
        return format_results([by_path[path] for path in paths]) + "\n"

    return render


def run_search(db_file: str, options: list[str]) -> int:
    return main(["--db", db_file, "search", *options])


SUCCESS_CASES = [
    pytest.param(BASE_OPTIONS, ["0-0-0", "1-1-0"], id="test_main_search_all_base"),
    pytest.param(
        ["--cannot-pop", "lead", "--min-pierce", "4"],
        [],
        id="test_main_search_min_pierce_above_all",
    ),
    pytest.param(
        [*BASE_OPTIONS, "--damage-type", "Sharp"],
        ["0-0-0"],
        id="test_main_search_damage_type_known",
    ),
    pytest.param(
        [*BASE_OPTIONS, "--sort", "projectile_pierce"],
        ["1-1-0", "0-0-0"],
        id="test_main_search_sort_whitelisted",
    ),
    pytest.param([*BASE_OPTIONS, "--limit", "1"], ["0-0-0"], id="test_main_search_limit_one"),
    pytest.param(
        ["--can-pop", "lead", "--min-pierce", "1"],
        ["2-0-0", "2-1-0"],
        id="test_main_search_can_pop_lead",
    ),
    pytest.param(["--min-pierce", "1"], ALL_PATHS, id="test_main_search_no_lead_flags"),
    pytest.param([*BASE_OPTIONS, "--camo"], [], id="test_main_search_camo"),
    pytest.param([*BASE_OPTIONS, "--no-camo"], ["0-0-0", "1-1-0"], id="test_main_search_no_camo"),
    pytest.param([], ALL_PATHS, id="test_main_search_no_filters"),
    pytest.param(
        [
            "--cannot-pop",
            "lead",
            "--min-pierce",
            "3",
            "--sort",
            "projectile_pierce",
            "--limit",
            "5",
        ],
        ["1-1-0"],
        id="test_main_search_epic_example",
    ),
]


@pytest.mark.parametrize(("options", "paths"), SUCCESS_CASES)
def test_main_search_success_cases(
    db_file: str, expected_table, capsys: pytest.CaptureFixture[str], options, paths
):
    exit_code = run_search(db_file, options)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    expected = expected_table(paths) if paths else NO_MATCH_OUTPUT
    assert captured.out == expected


def test_main_search_empty_database(
    tmp_path: Path, golden_csv_path: Path, capsys: pytest.CaptureFixture[str]
):
    empty_db = build_database_file(tmp_path / "empty.db", golden_csv_path, with_rows=False)

    exit_code = run_search(empty_db, BASE_OPTIONS)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out == NO_MATCH_OUTPUT


def test_main_search_min_pierce_not_a_number(db_file: str, capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as excinfo:
        run_search(db_file, ["--cannot-pop", "lead", "--min-pierce", "abc"])

    assert excinfo.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == (
        "btd6 search: error: argument --min-pierce: invalid float value: 'abc'"
    )


def test_main_search_sort_not_whitelisted(db_file: str, capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as excinfo:
        run_search(db_file, [*BASE_OPTIONS, "--sort", "bogus"])

    assert excinfo.value.code == 2
    assert (
        capsys.readouterr()
        .err.splitlines()[-1]
        .startswith("btd6 search: error: argument --sort: invalid choice: 'bogus'")
    )


def test_main_search_lead_in_both_flags(db_file: str, capsys: pytest.CaptureFixture[str]):
    exit_code = run_search(
        db_file, ["--can-pop", "lead", "--cannot-pop", "lead", "--min-pierce", "1"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == "--can-pop and --cannot-pop both list lead\n"
    assert captured.out == ""


def test_main_search_non_magic_rows_excluded(
    tmp_path: Path, golden_csv_path: Path, expected_table, capsys: pytest.CaptureFixture[str]
):
    mixed_db = build_database_file(tmp_path / "mixed.db", golden_csv_path, with_dart_monkey=True)

    exit_code = run_search(mixed_db, BASE_OPTIONS)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "Dart Monkey" not in captured.out
    assert captured.out == expected_table(["0-0-0", "1-1-0"])


def write_not_a_database(path: Path) -> str:
    path.write_text("hello")
    return str(path)


def test_main_search_database_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    missing_path = tmp_path / "missing.db"

    exit_code = run_search(str(missing_path), BASE_OPTIONS)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == (
        f'Database not found at {missing_path}. Run "python -m btd6 load" first.\n'
    )
    assert captured.out == ""
    assert not missing_path.exists()


def test_main_search_database_not_a_database(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    bad_file = write_not_a_database(tmp_path / "bad.db")

    exit_code = run_search(bad_file, BASE_OPTIONS)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == "Unexpected error: file is not a database\n"
    assert "Traceback" not in captured.err
    assert captured.out == ""


VALUE_ERROR_CASES = [
    pytest.param(
        ["--cannot-pop", "lead", "--min-pierce", "-1"],
        "min_pierce must be 0 or more, got -1.0\n",
        id="test_main_search_min_pierce_negative",
    ),
    pytest.param(
        [*BASE_OPTIONS, "--damage-type", "Bogus"],
        'Unknown damage type "Bogus". Valid types: Acid, Cold, Energy, Explosion, '
        "Fire, Frigid, Glacier, Normal, Plasma, Sharp, Shatter, Unknown\n",
        id="test_main_search_damage_type_unknown",
    ),
    pytest.param(
        [*BASE_OPTIONS, "--limit", "0"],
        "limit must be at least 1, got 0\n",
        id="test_main_search_limit_zero",
    ),
]


@pytest.mark.parametrize(("options", "expected_error"), VALUE_ERROR_CASES)
def test_main_search_query_value_errors(
    db_file: str, capsys: pytest.CaptureFixture[str], options, expected_error
):
    exit_code = run_search(db_file, options)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == expected_error
    assert captured.out == ""


def test_main_search_debug_traceback(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    bad_file = write_not_a_database(tmp_path / "bad.db")

    exit_code = main(["--debug", "--db", bad_file, "search"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Traceback" in captured.err
    assert "DatabaseError: file is not a database" in captured.err
    assert captured.err.index("Traceback") < captured.err.index("Unexpected error:")
    last_line = [line for line in captured.err.splitlines() if line.strip()][-1]
    assert "file is not a database" in last_line


def test_main_search_unrelated_value_error_is_unexpected(
    db_file: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    def raise_boom(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr("btd6.cli.search_upgrades", raise_boom)

    exit_code = run_search(db_file, BASE_OPTIONS)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == "Unexpected error: boom\n"
    assert captured.out == ""
