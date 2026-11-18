from __future__ import annotations

import sqlite3
from pathlib import Path

from btd6.db.connection import connect

__all__ = ["MIGRATIONS_DIR", "apply_migrations", "connect"]

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_script_atomically(connection: sqlite3.Connection, body: str, version: int) -> None:
    """Run a migration and its version bump in one transaction, or not at all."""
    try:
        connection.executescript(f"BEGIN;\n{body}\nPRAGMA user_version = {version};\nCOMMIT;")
    except sqlite3.Error:
        if connection.in_transaction:
            connection.rollback()
        raise


def apply_migrations(connection: sqlite3.Connection) -> list[str]:
    """Apply unapplied migrations in numeric order; return the names applied."""
    current = connection.execute("PRAGMA user_version").fetchone()[0]
    applied: list[str] = []
    for script in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(script.name.split("_", 1)[0])
        if version <= current:
            continue
        run_script_atomically(connection, script.read_text(), version)
        applied.append(script.name)
    return applied
