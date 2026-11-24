from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from btd6.db.connection import connect
from btd6.etl import fetch as wiki_fetch
from btd6.etl.pipeline import RefreshError, refresh_database
from tests.factories import IncomeSetFactory, RawBloonFactory
from tests.test_pipeline import ROUNDSET, fake_fetch_roundset, make_fetch, raising

pytestmark = pytest.mark.usefixtures("offline_costs_wiki")


def raw_bloons() -> list[dict[str, Any]]:
    return [
        RawBloonFactory(id="Red"),
        RawBloonFactory(id="Blue", parent_of="[[Red Bloon (BTD6)|Red Bloon]] ×1"),
        RawBloonFactory(id="Moab", is_moab="1"),
    ]


@pytest.fixture(autouse=True)
def offline_wiki(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wiki_fetch, "fetch_bloons", raw_bloons)
    monkeypatch.setattr(wiki_fetch, "fetch_roundset", fake_fetch_roundset)
    monkeypatch.setattr(wiki_fetch, "fetch_income_set", IncomeSetFactory)


@pytest.fixture
def connection() -> sqlite3.Connection:
    return connect(":memory:")


def count_rows(connection: sqlite3.Connection, table: str) -> int:
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_income_is_loaded_with_rounds(connection) -> None:
    result = refresh_database(connection, ("Druid",), fetch=make_fetch())
    assert result["Income"] == 6
    assert count_rows(connection, "income_thresholds") == 6
    assert count_rows(connection, "income_settings") == 1


def test_bloons_get_pop_cash_in_refresh(connection) -> None:
    refresh_database(connection, ("Druid",), fetch=make_fetch())
    rows = connection.execute("SELECT name, pop_cash FROM bloons").fetchall()
    assert {row["name"]: row["pop_cash"] for row in rows} == {"Red": 1, "Blue": 2, "Moab": 1}


def test_income_failure_keeps_everything_else(connection, monkeypatch) -> None:
    error = ValueError('Income set "DefaultIncomeSet" not found on the wiki')
    monkeypatch.setattr(wiki_fetch, "fetch_income_set", raising(error))
    with pytest.raises(RefreshError) as caught:
        refresh_database(connection, ("Druid",), fetch=make_fetch())
    assert list(caught.value.failures) == ["Income"]
    assert caught.value.loaded["Druid"] == 64
    assert count_rows(connection, "round_groups") == len(
        [group for rnd in ROUNDSET["rounds"] for group in rnd["bloonGroups"]]
    )
    assert count_rows(connection, "income_thresholds") == 0


def test_include_rounds_false_skips_income_fetch(connection, monkeypatch) -> None:
    monkeypatch.setattr(wiki_fetch, "fetch_income_set", raising(AssertionError("fetched")))
    refresh_database(connection, ("Druid",), fetch=make_fetch(), include_rounds=False)
    assert count_rows(connection, "income_thresholds") == 0


def test_second_run_leaves_income_unchanged(connection) -> None:
    refresh_database(connection, ("Druid",), fetch=make_fetch())
    refresh_database(connection, ("Druid",), fetch=make_fetch())
    assert count_rows(connection, "income_thresholds") == 6
    assert count_rows(connection, "income_settings") == 1
