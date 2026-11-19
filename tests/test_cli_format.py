from __future__ import annotations

import sqlite3
from pathlib import Path
from textwrap import dedent

import pytest

from btd6.cli import format_results
from btd6.query import UpgradeFilters, search_upgrades
from tests.test_query import (
    build_database,
    close_after,
    insert_tower,
    insert_upgrade,
    load_all_rows,
)


def expected_table(text: str) -> str:
    return dedent(text).strip("\n")


EXPECTED_TWO_ROWS = expected_table(
    """
           tower  path   type damage pierce range speed  rate camo lead black white purple glass frozen
    Super Monkey 0-0-0  Sharp      1      1    50   200 0.045   no   no   yes   yes    yes   yes     no
    Super Monkey 1-1-0 Energy      1      3    60   200 0.045   no   no   yes   yes     no    no    yes
    """  # noqa: E501
)
EXPECTED_NULL_STAT = expected_table(
    """
           tower  path   type damage pierce range speed  rate camo lead black white purple glass frozen
    Super Monkey 0-0-0  Sharp      1      -    50   200 0.045   no   no   yes   yes    yes   yes     no
    Super Monkey 1-1-0 Energy      1      3    60   200 0.045   no   no   yes   yes     no    no    yes
    """  # noqa: E501
)
EXPECTED_UNKNOWN_TYPE = expected_table(
    """
           tower  path    type damage pierce range speed  rate camo lead black white purple glass frozen
    Super Monkey 0-0-0 Unknown      1      1    50   200 0.045   no    -     -     -      -     -      -
    Super Monkey 1-1-0  Energy      1      3    60   200 0.045   no   no   yes   yes     no    no    yes
    """  # noqa: E501
)


def build_two_row_database(
    csv_path: Path, first_overrides: dict | None = None, first_type: str | None = None
) -> sqlite3.Connection:
    conn = build_database(csv_path, with_rows=False)
    tower_id = insert_tower(conn, "Super Monkey", "Magic")
    rows = load_all_rows(csv_path)
    insert_upgrade(
        conn, tower_id, rows["0-0-0"], damage_type=first_type, stat_overrides=first_overrides
    )
    insert_upgrade(conn, tower_id, rows["1-1-0"])
    conn.commit()
    return conn


def format_unfiltered_upgrades(conn: sqlite3.Connection) -> str:
    return format_results(search_upgrades(conn, UpgradeFilters()))


@pytest.fixture
def lead_free_output(golden_csv_path: Path):
    conn = build_database(golden_csv_path)
    rows = search_upgrades(conn, UpgradeFilters(can_pop_lead=False))
    yield format_results(rows)
    conn.close()


def test_format_results_two_rows(lead_free_output):
    assert lead_free_output == EXPECTED_TWO_ROWS


def test_format_results_no_rows():
    assert format_results([]) == "No upgrades match these filters."


@pytest.fixture
def full_conn(golden_csv_path: Path):
    yield from close_after(build_database(golden_csv_path, all_rows=True))


def test_format_results_no_truncation(full_conn):
    rows = search_upgrades(full_conn, UpgradeFilters())
    assert len(rows) == 64
    lines = format_results(rows).splitlines()
    assert len(lines) == 65
    assert all("..." not in line for line in lines)


@pytest.fixture
def null_pierce_conn(golden_csv_path: Path):
    yield from close_after(
        build_two_row_database(golden_csv_path, first_overrides={"projectile_pierce": None})
    )


def test_format_results_null_stat(null_pierce_conn):
    assert format_unfiltered_upgrades(null_pierce_conn) == EXPECTED_NULL_STAT


@pytest.fixture
def unknown_type_conn(golden_csv_path: Path):
    yield from close_after(build_two_row_database(golden_csv_path, first_type="Unknown"))


def test_format_results_unknown_damage_type(unknown_type_conn):
    assert format_unfiltered_upgrades(unknown_type_conn) == EXPECTED_UNKNOWN_TYPE


def test_format_results_fits_120_columns(lead_free_output):
    assert max(len(line) for line in lead_free_output.splitlines()) <= 120
