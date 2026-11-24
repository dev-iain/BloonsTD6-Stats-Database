from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from btd6.db.connection import connect
from btd6.etl import fetch
from btd6.etl import fetch as wiki_fetch
from btd6.etl.pipeline import RefreshError, refresh_database
from btd6.etl.towers import MAGIC_TOWERS
from tests.factories import IncomeSetFactory

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "super_monkey_resolved.json"
ROWS_PER_TOWER = 64

pytestmark = pytest.mark.usefixtures("offline_costs_wiki")

RAW_BLOONS = [
    {"id": "Red", "health": "1", "layers": "1", "rbe": "1", "is_moab": "", "speed": "25"},
    {"id": "Blue", "health": "1", "layers": "2", "rbe": "2", "is_moab": "", "speed": "35"},
    {"id": "Moab", "health": "200", "layers": "0", "rbe": "616", "is_moab": "1", "speed": "25"},
]
ROUNDSET = {
    "rounds": [
        {"bloonGroups": [{"bloon": "Red", "count": 20, "start": 0, "duration": 17.5}]},
        {"bloonGroups": [{"bloon": "Red", "count": 35, "start": 0, "duration": 19}]},
        {
            "bloonGroups": [
                {"bloon": "Red", "count": 5, "start": 0, "duration": 3},
                {"bloon": "BlueCamo", "count": 3, "start": 3, "duration": 2},
                {"bloon": "Red", "count": 2, "start": 6, "duration": 1},
            ]
        },
    ]
}


def fake_fetch_bloons() -> list[dict[str, Any]]:
    return [dict(raw) for raw in RAW_BLOONS]


def fake_fetch_roundset() -> dict[str, Any]:
    return copy.deepcopy(ROUNDSET)


def raising(error: Exception):
    def fail() -> Any:
        raise error

    return fail


@pytest.fixture(autouse=True)
def offline_rounds_wiki(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wiki_fetch, "fetch_bloons", fake_fetch_bloons)
    monkeypatch.setattr(wiki_fetch, "fetch_roundset", fake_fetch_roundset)
    monkeypatch.setattr(wiki_fetch, "fetch_income_set", IncomeSetFactory)


def load_tower_data() -> dict[str, Any]:
    """Flat `_NNN` nodes: resolve_all_codes returns them unchanged, giving 64 upgrades."""
    return json.loads(FIXTURE_PATH.read_text())


def make_fetch(failing: tuple[str, ...] = (), requested: list[str] | None = None):
    def fake_fetch(tower_name: str) -> dict[str, Any]:
        if requested is not None:
            requested.append(tower_name)
        if tower_name in failing:
            raise RuntimeError(f"wiki down for {tower_name}")
        return load_tower_data()

    return fake_fetch


@pytest.fixture
def connection() -> sqlite3.Connection:
    return connect(":memory:")


def count_upgrades(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM upgrades").fetchone()[0]


def upgrade_counts_by_tower(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute(
        "SELECT towers.name AS name, COUNT(*) AS total FROM upgrades "
        "JOIN towers ON towers.id = upgrades.tower_id GROUP BY towers.name"
    ).fetchall()
    return {row["name"]: row["total"] for row in rows}


def snapshot_tower(connection: sqlite3.Connection, tower_name: str) -> list[tuple[Any, ...]]:
    rows = connection.execute(
        "SELECT upgrades.* FROM upgrades JOIN towers ON towers.id = upgrades.tower_id "
        "WHERE towers.name = ? ORDER BY path",
        (tower_name,),
    ).fetchall()
    return [tuple(row)[2:] for row in rows]


def test_all_five_succeed_returns_counts(connection) -> None:
    result = refresh_database(connection, fetch=make_fetch())
    assert result == {
        **{name: ROWS_PER_TOWER for name in MAGIC_TOWERS},
        "Bloons": 3,
        "Rounds": 3,
        "Round groups": 5,
        "Income": 6,
    }


def test_all_five_succeed_loads_320_rows(connection) -> None:
    refresh_database(connection, fetch=make_fetch())
    assert count_upgrades(connection) == 320
    assert upgrade_counts_by_tower(connection) == {name: ROWS_PER_TOWER for name in MAGIC_TOWERS}


def test_default_tower_names_uses_magic_towers(connection) -> None:
    requested: list[str] = []
    refresh_database(connection, fetch=make_fetch(requested=requested))
    assert requested == list(MAGIC_TOWERS)


def test_explicit_tower_names_limit_the_refresh(connection) -> None:
    result = refresh_database(connection, ("Druid",), fetch=make_fetch(), include_rounds=False)
    assert result == {"Druid": ROWS_PER_TOWER}
    assert upgrade_counts_by_tower(connection) == {"Druid": ROWS_PER_TOWER}


def test_fresh_in_memory_database_gets_migrated(connection) -> None:
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
    refresh_database(connection, ("Druid",), fetch=make_fetch())
    assert connection.execute("PRAGMA user_version").fetchone()[0] > 0
    assert connection.execute("SELECT COUNT(*) FROM damage_types").fetchone()[0] > 0


def test_second_run_is_noop_in_effect(connection) -> None:
    refresh_database(connection, fetch=make_fetch())
    before = snapshot_tower(connection, "Druid")
    second = refresh_database(connection, fetch=make_fetch())
    assert second["Round groups"] == 5
    assert {name: second[name] for name in MAGIC_TOWERS} == {
        n: ROWS_PER_TOWER for n in MAGIC_TOWERS
    }
    assert count_upgrades(connection) == 320
    assert snapshot_tower(connection, "Druid") == before


def test_one_failure_raises_refresh_error_and_loads_others(connection) -> None:
    with pytest.raises(RefreshError) as caught:
        refresh_database(connection, fetch=make_fetch(failing=("Ninja Monkey",)))
    healthy = [name for name in MAGIC_TOWERS if name != "Ninja Monkey"]
    assert {name: caught.value.loaded[name] for name in healthy} == {
        name: ROWS_PER_TOWER for name in healthy
    }
    assert "Ninja Monkey" not in caught.value.loaded
    assert list(caught.value.failures) == ["Ninja Monkey"]
    assert isinstance(caught.value.failures["Ninja Monkey"], RuntimeError)
    assert upgrade_counts_by_tower(connection) == {name: ROWS_PER_TOWER for name in healthy}


def test_refresh_error_is_an_exception_subclass() -> None:
    assert issubclass(RefreshError, Exception)


def test_failed_tower_previous_rows_untouched(connection) -> None:
    refresh_database(connection, ("Wizard Monkey",), fetch=make_fetch())
    before = snapshot_tower(connection, "Wizard Monkey")
    with pytest.raises(RefreshError):
        refresh_database(connection, fetch=make_fetch(failing=("Wizard Monkey",)))
    assert snapshot_tower(connection, "Wizard Monkey") == before
    assert count_upgrades(connection) == 320


def test_multiple_failures_are_all_collected(connection) -> None:
    failing = ("Super Monkey", "Druid")
    with pytest.raises(RefreshError) as caught:
        refresh_database(connection, fetch=make_fetch(failing=failing))
    assert set(caught.value.failures) == set(failing)
    assert set(caught.value.loaded) - {"Bloons", "Rounds", "Round groups", "Income"} == (
        set(MAGIC_TOWERS) - set(failing)
    )


def test_never_uses_data_json(connection, monkeypatch, tmp_path) -> None:
    real_open = Path.read_text

    def guarded_read(self: Path, *args: Any, **kwargs: Any) -> str:
        assert self.name != "data.json"
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    refresh_database(connection, ("Druid",), fetch=make_fetch())


@pytest.mark.parametrize(
    ("failures", "expected"),
    [
        ({"Wizard Monkey": ValueError("x")}, "refresh failed for: Wizard Monkey"),
        (
            {"Wizard Monkey": ValueError("x"), "Super Monkey": KeyError("y")},
            "refresh failed for: Wizard Monkey, Super Monkey",
        ),
    ],
)
def test_refresh_error_message_lists_failed_towers(
    failures: dict[str, Exception], expected: str
) -> None:
    assert str(RefreshError({}, failures)) == expected


def fail_costs_for(monkeypatch: pytest.MonkeyPatch, tower_name: str) -> None:
    real_fetch_costs = fetch.fetch_costs

    def flaky_fetch_costs(name: str) -> dict[str, Any]:
        if name == tower_name:
            raise RuntimeError(f"cost table down for {name}")
        return real_fetch_costs(name)

    monkeypatch.setattr(fetch, "fetch_costs", flaky_fetch_costs)


def test_cost_fetch_failure_writes_no_upgrades(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_costs_for(monkeypatch, "Druid")
    with pytest.raises(RefreshError) as caught:
        refresh_database(connection, ["Super Monkey", "Druid"], fetch=make_fetch())
    assert "Druid" not in upgrade_counts_by_tower(connection)
    assert "Druid" not in caught.value.loaded
    assert caught.value.loaded["Super Monkey"] == ROWS_PER_TOWER
    assert "Druid" not in caught.value.loaded


def test_cost_fetch_failure_keeps_previous_rows(
    connection: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    refresh_database(connection, ["Druid"], fetch=make_fetch())
    before = snapshot_tower(connection, "Druid")
    fail_costs_for(monkeypatch, "Druid")
    with pytest.raises(RefreshError):
        refresh_database(connection, ["Druid"], fetch=make_fetch())
    assert snapshot_tower(connection, "Druid") == before


def count_rows(connection: sqlite3.Connection, table: str) -> int:
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_rounds_are_loaded_after_towers(connection) -> None:
    refresh_database(connection, ("Druid",), fetch=make_fetch())
    assert count_rows(connection, "bloons") == 3
    assert count_rows(connection, "rounds") == 3
    assert count_rows(connection, "round_groups") == 5


def test_include_rounds_false_skips_fetches(connection, monkeypatch) -> None:
    monkeypatch.setattr(wiki_fetch, "fetch_bloons", raising(AssertionError("fetched")))
    result = refresh_database(connection, ("Druid",), fetch=make_fetch(), include_rounds=False)
    assert result == {"Druid": ROWS_PER_TOWER}
    assert count_rows(connection, "bloons") == 0


def test_bloons_failure_skips_rounds_but_keeps_towers(connection) -> None:
    error = ValueError("Wiki cargo query returned no rows")
    with pytest.raises(RefreshError) as caught:
        refresh_database(
            connection, ("Druid",), fetch=make_fetch(), fetch_bloon_rows=raising(error)
        )
    assert list(caught.value.failures) == ["Bloons"]
    assert caught.value.loaded == {"Druid": ROWS_PER_TOWER, "Income": 6}
    assert count_rows(connection, "rounds") == 0


def test_roundset_failure_keeps_bloons_and_towers(connection) -> None:
    error = ValueError('Roundset "DefaultRoundSet" not found on the wiki')
    with pytest.raises(RefreshError) as caught:
        refresh_database(connection, ("Druid",), fetch=make_fetch(), fetch_roundset=raising(error))
    assert list(caught.value.failures) == ["Rounds"]
    assert caught.value.loaded == {"Druid": ROWS_PER_TOWER, "Bloons": 3, "Income": 6}
    assert count_rows(connection, "bloons") == 3
    assert count_rows(connection, "round_groups") == 0


def test_second_run_leaves_round_counts_unchanged(connection) -> None:
    refresh_database(connection, ("Druid",), fetch=make_fetch())
    refresh_database(connection, ("Druid",), fetch=make_fetch())
    assert count_rows(connection, "bloons") == 3
    assert count_rows(connection, "round_groups") == 5
