from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def apply_migrations(connection: sqlite3.Connection) -> list[str]:
    """Apply unapplied migrations in numeric order; return the names applied."""
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    applied: list[str] = []
    for script in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(script.name.split("_", 1)[0])
        if version <= current:
            continue
        connection.executescript(script.read_text())
        connection.execute(f"PRAGMA user_version = {version}")
        applied.append(script.name)
    return applied
