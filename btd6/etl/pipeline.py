from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from typing import Any

from btd6.db.cost_loader import load_costs
from btd6.db.loader import load_tower
from btd6.db.round_loader import load_bloons, load_income, load_rounds
from btd6.db.seed import initialize_database
from btd6.etl import fetch as wiki
from btd6.etl.extract import extract_bloon_rows, extract_round_rows
from btd6.etl.towers import MAGIC_TOWERS

BLOONS_KEY = "Bloons"
ROUNDS_KEY = "Rounds"
ROUND_GROUPS_KEY = "Round groups"
INCOME_KEY = "Income"
ROUND_KEYS = (BLOONS_KEY, ROUNDS_KEY, ROUND_GROUPS_KEY)


class RefreshError(Exception):
    """Raised after a refresh in which at least one tower, the bloons or the rounds failed."""

    def __init__(self, loaded: dict[str, int], failures: dict[str, Exception]) -> None:
        super().__init__(f"refresh failed for: {', '.join(failures)}")
        self.loaded = loaded
        self.failures = failures


def run_step(
    key: str,
    action: Callable[[], int],
    loaded: dict[str, int],
    failures: dict[str, Exception],
) -> bool:
    try:
        loaded[key] = action()
    except Exception as error:
        failures[key] = error
        return False
    return True


def load_one_tower(
    connection: sqlite3.Connection, tower_name: str, fetch: Callable[[str], dict[str, Any]]
) -> int:
    resolved = wiki.resolve_all_codes(fetch(tower_name))
    costs = wiki.fetch_costs(tower_name)
    written = load_tower(connection, tower_name, resolved, costs["category"])
    load_costs(connection, tower_name, costs)
    return written


def refresh_towers(
    connection: sqlite3.Connection,
    tower_names: Iterable[str],
    fetch: Callable[[str], dict[str, Any]],
    loaded: dict[str, int],
    failures: dict[str, Exception],
) -> None:
    for tower_name in tower_names:
        run_step(
            tower_name,
            lambda name=tower_name: load_one_tower(connection, name, fetch),
            loaded,
            failures,
        )


def read_bloon_ids(connection: sqlite3.Connection) -> dict[str, int]:
    return {row[0]: row[1] for row in connection.execute("SELECT name, id FROM bloons")}


def load_round_steps(
    connection: sqlite3.Connection,
    fetch_roundset: Callable[[], dict[str, Any]],
    loaded: dict[str, int],
) -> int:
    rows = extract_round_rows(fetch_roundset())
    loaded[ROUND_GROUPS_KEY] = load_rounds(connection, rows, read_bloon_ids(connection))
    return len({row["round"] for row in rows})


def refresh_rounds(
    connection: sqlite3.Connection,
    fetch_bloon_rows: Callable[[], list[dict[str, Any]]],
    fetch_roundset: Callable[[], dict[str, Any]],
    loaded: dict[str, int],
    failures: dict[str, Exception],
) -> None:
    """Load bloons, then rounds 1-100; a failed bloons step skips the rounds step."""
    bloons_loaded = run_step(
        BLOONS_KEY,
        lambda: load_bloons(connection, extract_bloon_rows(fetch_bloon_rows())),
        loaded,
        failures,
    )
    if bloons_loaded:
        run_step(
            ROUNDS_KEY,
            lambda: load_round_steps(connection, fetch_roundset, loaded),
            loaded,
            failures,
        )


def refresh_income(
    connection: sqlite3.Connection,
    fetch_income_set: Callable[[], dict[str, Any]],
    loaded: dict[str, int],
    failures: dict[str, Exception],
) -> None:
    run_step(INCOME_KEY, lambda: load_income(connection, fetch_income_set()), loaded, failures)


def refresh_rounds_with_defaults(
    connection: sqlite3.Connection,
    fetch_bloon_rows: Callable[[], list[dict[str, Any]]] | None,
    fetch_roundset: Callable[[], dict[str, Any]] | None,
    loaded: dict[str, int],
    failures: dict[str, Exception],
) -> None:
    refresh_rounds(
        connection,
        fetch_bloon_rows or wiki.fetch_bloons,
        fetch_roundset or wiki.fetch_roundset,
        loaded,
        failures,
    )


def refresh_database(
    connection: sqlite3.Connection,
    tower_names: Iterable[str] | None = None,
    fetch: Callable[[str], dict[str, Any]] = wiki.fetch_tower_module,
    include_rounds: bool = True,
    fetch_bloon_rows: Callable[[], list[dict[str, Any]]] | None = None,
    fetch_roundset: Callable[[], dict[str, Any]] | None = None,
    fetch_income_set: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Fetch and load each tower, then bloons and rounds, returning {name: rows written}.

    A failing tower does not stop the others (its previous rows stay intact because each
    load is one transaction). Stats and costs are both fetched before anything is written,
    so a failed download never leaves a tower with stats but no costs.
    Failures are raised together as `RefreshError` only after everything ran, so one bad
    fetch never hides the healthy results. With `include_rounds`, the result also holds
    "Bloons", "Rounds" (round count), "Round groups" and "Income" (thresholds).
    """
    if tower_names is None:
        tower_names = MAGIC_TOWERS
    initialize_database(connection)
    loaded: dict[str, int] = {}
    failures: dict[str, Exception] = {}
    refresh_towers(connection, tower_names, fetch, loaded, failures)
    if include_rounds:
        refresh_rounds_with_defaults(connection, fetch_bloon_rows, fetch_roundset, loaded, failures)
        refresh_income(connection, fetch_income_set or wiki.fetch_income_set, loaded, failures)
    if failures:
        raise RefreshError(loaded, failures)
    return loaded
