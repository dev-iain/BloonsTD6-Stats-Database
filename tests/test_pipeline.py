from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from btd6.db.connection import connect
from btd6.etl.pipeline import RefreshError, refresh_database
from btd6.etl.towers import MAGIC_TOWERS

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "super_monkey_resolved.json"
ROWS_PER_TOWER = 64


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
    assert result == {name: ROWS_PER_TOWER for name in MAGIC_TOWERS}


def test_all_five_succeed_loads_320_rows(connection) -> None:
    refresh_database(connection, fetch=make_fetch())
    assert count_upgrades(connection) == 320
    assert upgrade_counts_by_tower(connection) == {name: ROWS_PER_TOWER for name in MAGIC_TOWERS}


def test_default_tower_names_uses_magic_towers(connection) -> None:
    requested: list[str] = []
    refresh_database(connection, fetch=make_fetch(requested=requested))
    assert requested == list(MAGIC_TOWERS)


def test_explicit_tower_names_limit_the_refresh(connection) -> None:
    result = refresh_database(connection, ("Druid",), fetch=make_fetch())
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
    assert second == {name: ROWS_PER_TOWER for name in MAGIC_TOWERS}
    assert count_upgrades(connection) == 320
    assert snapshot_tower(connection, "Druid") == before


def test_one_failure_raises_refresh_error_and_loads_others(connection) -> None:
    with pytest.raises(RefreshError) as caught:
        refresh_database(connection, fetch=make_fetch(failing=("Ninja Monkey",)))
    healthy = [name for name in MAGIC_TOWERS if name != "Ninja Monkey"]
    assert caught.value.loaded == {name: ROWS_PER_TOWER for name in healthy}
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
    assert set(caught.value.loaded) == set(MAGIC_TOWERS) - set(failing)


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
