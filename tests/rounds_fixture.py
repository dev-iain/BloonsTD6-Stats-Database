from __future__ import annotations

import sqlite3

from btd6.db import apply_migrations, connect

BLOONS = {"Red": 1, "Blue": 2, "Pink": 5, "Lead": 23, "Ceramic": 104, "Moab": 616}
LAYERS = {"Red": 1, "Blue": 2, "Pink": 5, "Lead": 4, "Ceramic": 10, "Moab": 1}
LEAD_RBE_FORT = 30
SPECIAL_ROUNDS: dict[int, list[tuple[str, int, bool]]] = {
    1: [("Red", 20, False)],
    3: [("Red", 5, False), ("Blue", 3, False), ("Red", 2, False)],
    24: [("Blue", 10, True)],
    27: [("Lead", 6, False)],
    35: [("Ceramic", 3, False)],
    40: [("Pink", 20, False), ("Moab", 1, False)],
}
LOADED_ROUNDS = 40


def build_rounds_db(
    extra_rounds: dict[int, list[tuple[str, int, bool]]] | None = None,
) -> sqlite3.Connection:
    connection = connect(":memory:")
    apply_migrations(connection)
    bloon_ids = {}
    for name, rbe in BLOONS.items():
        cursor = connection.execute(
            "INSERT INTO bloons (name, rbe, rbe_fort, layers, is_moab, has_lead)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                name,
                rbe,
                LEAD_RBE_FORT if name == "Lead" else None,
                LAYERS[name],
                int(name == "Moab"),
                int(name == "Lead"),
            ),
        )
        bloon_ids[name] = cursor.lastrowid
    groups = {**SPECIAL_ROUNDS, **(extra_rounds or {})}
    for number in range(1, LOADED_ROUNDS + 1):
        connection.execute("INSERT INTO rounds (round) VALUES (?)", (number,))
        for index, (name, count, camo) in enumerate(groups.get(number, [("Red", 1, False)])):
            connection.execute(
                "INSERT INTO round_groups (round, group_index, bloon_id, is_camo, is_regrow,"
                " is_fortified, count, start, duration) VALUES (?, ?, ?, ?, 0, 0, ?, 0, 1)",
                (number, index, bloon_ids[name], int(camo), count),
            )
    connection.commit()
    return connection
