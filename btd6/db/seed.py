from __future__ import annotations

import sqlite3

from btd6.db import apply_migrations
from btd6.etl.extract import BLOON_PROPERTIES, DAMAGE_TYPES

POP_COLUMNS = [f"can_pop_{name.lower()}" for name in BLOON_PROPERTIES]

INSERT_SQL = (
    f"INSERT INTO damage_types (name, {', '.join(POP_COLUMNS)}) "
    f"VALUES (?, {', '.join('?' * len(POP_COLUMNS))}) "
    "ON CONFLICT (name) DO UPDATE SET "
    + ", ".join(f"{column} = excluded.{column}" for column in POP_COLUMNS)
)


def damage_type_rows() -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = [
        (name, *(int(prop not in cannot_pop) for prop in BLOON_PROPERTIES))
        for name, cannot_pop in DAMAGE_TYPES.values()
    ]
    rows.append(("Unknown", *([None] * len(BLOON_PROPERTIES))))
    return rows


def seed_lookup_tables(connection: sqlite3.Connection) -> None:
    """Insert every DAMAGE_TYPES entry plus Unknown; safe to call repeatedly."""
    with connection:
        connection.executemany(INSERT_SQL, damage_type_rows())


def initialize_database(connection: sqlite3.Connection) -> None:
    """Migrate to the latest schema, then seed the lookup tables."""
    apply_migrations(connection)
    seed_lookup_tables(connection)
