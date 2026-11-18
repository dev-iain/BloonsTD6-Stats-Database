from __future__ import annotations

import sqlite3
from pathlib import Path

from btd6.etl.fetch import PROJECT_ROOT

DEFAULT_DATABASE_PATH = PROJECT_ROOT / "btd6.db"


def connect(database_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a database (default: btd6.db in the project root) with foreign keys on."""
    if database_path is None:
        database_path = DEFAULT_DATABASE_PATH
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection
