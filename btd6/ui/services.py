from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from btd6.query import UpgradeFilters
from btd6.ui.presenters import DatabaseMissingError
from btd6.ui.search_viewmodel import rows_to_cells


def run_query(
    database_path: str,
    filters: UpgradeFilters,
    sort_by: str | None,
    descending: bool,
    limit: int | None = None,
) -> list[tuple[str, ...]]:
    """Open a private connection (worker thread), search, and format rows for display."""
    if not Path(database_path).exists():
        raise DatabaseMissingError(database_path)
    from btd6.db import connect
    from btd6.query import search_upgrades

    connection = connect(database_path)
    try:
        rows = search_upgrades(
            connection, filters, sort_by=sort_by, descending=descending, limit=limit
        )
        return rows_to_cells(rows)
    except sqlite3.OperationalError as error:
        if "no such table" in str(error):
            raise DatabaseMissingError(database_path) from error
        raise
    finally:
        connection.close()


def list_damage_types(database_path: str) -> list[str]:
    """Damage type names for the filter dropdown; empty when nothing is loaded yet."""
    if not Path(database_path).exists():
        return []
    from btd6.db import connect

    connection = connect(database_path)
    try:
        rows = connection.execute("SELECT name FROM damage_types ORDER BY name").fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()
    return [row["name"] for row in rows]


def describe_load_failure(error: Exception) -> str:
    from requests import ConnectionError as WikiConnectionError

    from btd6.etl.pipeline import RefreshError

    if isinstance(error, RefreshError):
        if any(isinstance(item, WikiConnectionError) for item in error.failures.values()):
            return "could not reach the wiki; check your connection"
        return "could not load: " + ", ".join(error.failures)
    return str(error) or type(error).__name__


def load_database(database_path: str, report: Callable[[str], None]) -> str:
    """Run the existing refresh pipeline with its own connection; return a summary."""
    from btd6.db import connect
    from btd6.etl.pipeline import refresh_database
    from btd6.etl.towers import MAGIC_TOWERS

    connection = connect(database_path)
    try:
        total = 0
        for index, tower_name in enumerate(MAGIC_TOWERS, start=1):
            report(f"Loading {tower_name} ({index} of {len(MAGIC_TOWERS)})...")
            total += refresh_database(connection, [tower_name])[tower_name]
    except Exception as error:
        raise RuntimeError(describe_load_failure(error)) from error
    finally:
        connection.close()
    return f"Loaded {total} upgrades"
