from __future__ import annotations

import copy
import sqlite3
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.db import connect
from btd6.db.loader import load_tower
from btd6.db.seed import initialize_database
from tests.factories import (
    EffectFactory,
    make_attack,
    make_stats,
    ninja_003,
    with_effects,
)

GLUE_NAME = "Damage over time"


def glue_stats(*named: tuple[str, dict[str, Any]], damage: float = 1) -> dict[str, Any]:
    projectile = with_effects({"damage": damage, "pierce": 1}, *named)
    return make_stats(make_attack("Attack", 1, {"Projectile": projectile}))


def effect_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT e.*, d.name AS type_name, p.name AS projectile_name"
        " FROM projectile_effects e JOIN damage_types d ON d.id = e.damage_type_id"
        " JOIN projectiles p ON p.id = e.projectile_id ORDER BY e.id"
    ).fetchall()


def load(database: sqlite3.Connection, stats: dict[str, Any]) -> None:
    load_tower(database, "Glue Gunner", {"_200": stats}, "Support")


def test_load_tower_stores_effect_row(database) -> None:
    load(database, glue_stats((GLUE_NAME, EffectFactory())))
    (row,) = effect_rows(database)
    assert (row["effect_index"], row["name"], row["projectile_name"]) == (
        0,
        GLUE_NAME,
        "Projectile",
    )
    assert (row["damage"], row["tick_interval"], row["lifespan"]) == (1, 2, 11)
    assert (row["trigger_immediate"], row["moab_bonus_damage"], row["moab_only"]) == (0, None, 0)
    assert row["type_name"] == "Acid"


def test_load_tower_without_effects_stores_none(database) -> None:
    load_tower(database, "Ninja Monkey", {"_003": ninja_003()}, "Primary")
    assert effect_rows(database) == []


def test_load_tower_skips_non_damaging_effects(database) -> None:
    load(database, glue_stats(("Freeze", {"lifespan": 2}), (GLUE_NAME, EffectFactory())))
    (row,) = effect_rows(database)
    assert (row["effect_index"], row["name"]) == (1, GLUE_NAME)


def test_load_tower_stores_flags_and_bonus(database) -> None:
    effect = EffectFactory(triggerImmediate=True, damageModifierForMoabs=3, filterOutNonMoabs=True)
    load(database, glue_stats((GLUE_NAME, effect)))
    (row,) = effect_rows(database)
    assert (row["trigger_immediate"], row["moab_bonus_damage"], row["moab_only"]) == (1, 3, 1)


def test_load_tower_effect_order_preserved(database) -> None:
    named = [(f"Effect {number}", EffectFactory(damage=number + 1)) for number in range(3)]
    load(database, glue_stats(*named))
    assert [(row["effect_index"], row["damage"]) for row in effect_rows(database)] == [
        (0, 1),
        (1, 2),
        (2, 3),
    ]


def test_load_tower_effect_unknown_damage_type(database) -> None:
    load(database, glue_stats((GLUE_NAME, EffectFactory(immuneBloonProperties=3))))
    assert effect_rows(database)[0]["type_name"] == "Unknown"


def test_load_tower_effect_damage_type_independent_of_projectile(database) -> None:
    stats = glue_stats((GLUE_NAME, EffectFactory(immuneBloonProperties=0)))
    stats["attacks"]["Attack"]["projectiles"]["Projectile"]["immuneBloonProperties"] = 64
    load(database, stats)
    assert effect_rows(database)[0]["type_name"] == "Normal"


def test_load_tower_effect_on_each_projectile(database) -> None:
    projectiles = {
        "First": with_effects({"damage": 1}, ("One", EffectFactory())),
        "Second": with_effects({"damage": 1}, ("Two", EffectFactory(damage=4))),
    }
    load(database, make_stats(make_attack("Attack", 1, projectiles)))
    assert [(row["projectile_name"], row["name"]) for row in effect_rows(database)] == [
        ("First", "One"),
        ("Second", "Two"),
    ]


def test_reload_replaces_effects(database) -> None:
    load(database, glue_stats((GLUE_NAME, EffectFactory()), ("Second", EffectFactory())))
    load(database, glue_stats((GLUE_NAME, EffectFactory(damage=9))))
    rows = effect_rows(database)
    assert [(row["name"], row["damage"]) for row in rows] == [(GLUE_NAME, 9)]


def test_reload_without_effects_removes_them(database) -> None:
    load(database, glue_stats((GLUE_NAME, EffectFactory())))
    load(database, glue_stats())
    assert effect_rows(database) == []


def test_reload_same_data_is_idempotent(database) -> None:
    stats = glue_stats((GLUE_NAME, EffectFactory()))
    load(database, stats)
    first = [tuple(row)[1:] for row in effect_rows(database)]
    load(database, copy.deepcopy(stats))
    assert [tuple(row)[1:] for row in effect_rows(database)] == first


def test_reload_other_tower_keeps_effects(database) -> None:
    load(database, glue_stats((GLUE_NAME, EffectFactory())))
    load_tower(database, "Ninja Monkey", {"_003": ninja_003()}, "Primary")
    assert len(effect_rows(database)) == 1


@settings(max_examples=25, deadline=None)
@given(st.lists(st.tuples(st.integers(1, 40), st.floats(0.1, 5)), max_size=5))
def test_load_tower_effect_count_matches_extraction(pairs: list[tuple[int, float]]) -> None:
    connection = connect(":memory:")
    initialize_database(connection)
    named = [
        (f"E{number}", EffectFactory(damage=damage, interval=interval))
        for number, (damage, interval) in enumerate(pairs)
    ]
    for _ in range(2):
        load(connection, glue_stats(*named))
    assert len(effect_rows(connection)) == len(pairs)
    connection.close()
