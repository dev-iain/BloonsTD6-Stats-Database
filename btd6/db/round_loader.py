from __future__ import annotations

import sqlite3
from typing import Any

from btd6.etl.extract import extract_income_thresholds, split_bloon_name

BLOON_COLUMNS = (
    "health",
    "health_fort",
    "layers",
    "rbe",
    "rbe_fort",
    "pop_cash",
    "pop_cash_super",
    "is_moab",
    "speed",
)
UPSERT_BLOON_SQL = (
    "INSERT INTO bloons (name, "
    + ", ".join(BLOON_COLUMNS)
    + ") VALUES (?, "
    + ", ".join("?" * len(BLOON_COLUMNS))
    + ") ON CONFLICT (name) DO UPDATE SET "
    + ", ".join(f"{column} = excluded.{column}" for column in BLOON_COLUMNS)
)
INSERT_GROUP_SQL = (
    "INSERT INTO round_groups (round, group_index, bloon_id, is_camo, is_regrow, is_fortified, "
    "count, start, duration) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def bloon_params(row: dict[str, Any]) -> tuple[Any, ...]:
    values = [row.get(column) for column in BLOON_COLUMNS]
    values[BLOON_COLUMNS.index("is_moab")] = (
        int(row["is_moab"]) if isinstance(row["is_moab"], bool) else row["is_moab"]
    )
    return (row["name"], *values)


def delete_missing_bloons(connection: sqlite3.Connection, names: list[str]) -> None:
    placeholders = ", ".join("?" * len(names))
    connection.execute(f"DELETE FROM bloons WHERE name NOT IN ({placeholders})", names)


def load_bloons(connection: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    """Upsert bloons by name, keeping ids that round groups reference.

    Bloons absent from `rows` are deleted; one still used by a round group makes the
    whole call fail with `sqlite3.IntegrityError` and roll back. Returns `len(rows)`.
    """
    with connection:
        connection.executemany(UPSERT_BLOON_SQL, [bloon_params(row) for row in rows])
        delete_missing_bloons(connection, [row["name"] for row in rows])
    return len(rows)


def group_params(row: dict[str, Any], bloon_ids: dict[str, int]) -> tuple[Any, ...]:
    base, is_camo, is_regrow, is_fortified = split_bloon_name(row["bloon"])
    if base not in bloon_ids:
        raise ValueError(f'Unknown bloon "{base}" in round {row["round"]}')
    return (
        row["round"],
        row["group_index"],
        bloon_ids[base],
        int(is_camo),
        int(is_regrow),
        int(is_fortified),
        row["count"],
        row["start"],
        row["duration"],
    )


def load_rounds(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
    bloon_ids: dict[str, int],
) -> int:
    """Replace every round and group with `rows` in one transaction.

    Returns the number of groups written.
    """
    with connection:
        connection.execute("DELETE FROM round_groups")
        connection.execute("DELETE FROM rounds")
        round_numbers = sorted({row["round"] for row in rows})
        connection.executemany(
            "INSERT INTO rounds (round) VALUES (?)", [(n,) for n in round_numbers]
        )
        connection.executemany(INSERT_GROUP_SQL, [group_params(row, bloon_ids) for row in rows])
    return len(rows)


def load_income(connection: sqlite3.Connection, income_set: dict[str, Any]) -> int:
    """Replace the income thresholds and the final multiplier in one transaction.

    Returns the number of thresholds written.
    """
    rows = extract_income_thresholds(income_set)
    with connection:
        connection.execute("DELETE FROM income_thresholds")
        connection.executemany(
            "INSERT INTO income_thresholds (max_round, multiplier) VALUES (?, ?)",
            [(row["max_round"], row["multiplier"]) for row in rows],
        )
        connection.execute(
            "INSERT INTO income_settings (id, final_multiplier) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET final_multiplier = excluded.final_multiplier",
            (income_set["finalMultiplier"],),
        )
    return len(rows)
