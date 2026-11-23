from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from typing import Any

from btd6.db.cost_loader import load_costs
from btd6.db.loader import load_tower
from btd6.db.seed import initialize_database
from btd6.etl import fetch as wiki
from btd6.etl.towers import MAGIC_TOWERS


class RefreshError(Exception):
    """Raised after a refresh in which at least one tower failed."""

    def __init__(self, loaded: dict[str, int], failures: dict[str, Exception]) -> None:
        super().__init__(f"refresh failed for: {', '.join(failures)}")
        self.loaded = loaded
        self.failures = failures


def refresh_database(
    connection: sqlite3.Connection,
    tower_names: Iterable[str] | None = None,
    fetch: Callable[[str], dict[str, Any]] = wiki.fetch_tower_module,
) -> dict[str, int]:
    """Fetch and load each tower, returning {tower: upgrades written}.

    A failing tower does not stop the others (its previous rows stay intact because each
    load is one transaction). Failures are raised together as `RefreshError` only after
    the loop, so one bad fetch never hides the healthy towers' results.
    """
    if tower_names is None:
        tower_names = MAGIC_TOWERS
    initialize_database(connection)
    loaded: dict[str, int] = {}
    failures: dict[str, Exception] = {}
    for tower_name in tower_names:
        try:
            resolved = wiki.resolve_all_codes(fetch(tower_name))
            loaded[tower_name] = load_tower(connection, tower_name, resolved)
            load_costs(connection, tower_name, wiki.fetch_costs(tower_name))
        except Exception as error:
            failures[tower_name] = error
    if failures:
        raise RefreshError(loaded, failures)
    return loaded
