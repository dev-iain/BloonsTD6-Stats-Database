from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from btd6.query import UpgradeFilters
from btd6.ui.presenters import TABLE_COLUMNS, DatabaseMissingError
from btd6.ui.services import describe_load_failure, load_database, run_query
from tests.test_query import build_database


@pytest.fixture
def database_path(tmp_path: Path, golden_csv_path: Path) -> str:
    path = str(tmp_path / "ui.db")
    connection = build_database(golden_csv_path, path=path)
    connection.commit()
    connection.close()
    return path


def test_run_query_returns_display_tuples(database_path: str) -> None:
    rows = run_query(database_path, UpgradeFilters(), None, False)
    assert rows
    assert all(len(row) == len(TABLE_COLUMNS) for row in rows)
    assert all(isinstance(cell, str) for row in rows for cell in row)


def test_run_query_sorts_in_sql(database_path: str) -> None:
    rows = run_query(database_path, UpgradeFilters(), "projectile_damage", True)
    damages = [float(row[4]) for row in rows if row[4] != "-"]
    assert damages == sorted(damages, reverse=True)


def test_run_query_missing_file_raises_and_creates_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "nope.db"
    with pytest.raises(DatabaseMissingError):
        run_query(str(missing), UpgradeFilters(), None, False)
    assert not missing.exists()


def test_run_query_empty_database_file_is_missing(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    with pytest.raises(DatabaseMissingError):
        run_query(str(path), UpgradeFilters(), None, False)


def test_describe_load_failure_for_network_error() -> None:
    import requests

    from btd6.etl.pipeline import RefreshError

    error = RefreshError({}, {"Wizard Monkey": requests.ConnectionError("down")})
    assert "wiki" in describe_load_failure(error)


def test_load_database_reports_each_tower_and_summarizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from btd6.etl import pipeline

    def fake_refresh(
        connection: sqlite3.Connection, tower_names: list[str], fetch: object = None
    ) -> dict[str, int]:
        return {tower_names[0]: 2}

    monkeypatch.setattr(pipeline, "refresh_database", fake_refresh)
    messages: list[str] = []
    summary = load_database(str(tmp_path / "x.db"), messages.append)
    assert messages
    assert summary.startswith("Loaded ")


def test_load_database_wraps_failures_in_readable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from btd6.etl import pipeline

    def failing(
        connection: sqlite3.Connection, tower_names: list[str], fetch: object = None
    ) -> None:
        raise ValueError("bad payload")

    monkeypatch.setattr(pipeline, "refresh_database", failing)
    with pytest.raises(RuntimeError, match="bad payload"):
        load_database(str(tmp_path / "x.db"), lambda text: None)
