from __future__ import annotations

import copy
import sqlite3
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.db.loader import load_tower
from tests.factories import (
    UNLIMITED,
    alchemist_220,
    druid_030,
    druid_400,
    make_attack,
    make_stats,
    ninja_003,
)

ABILITY_ONE = {"_order": ["Ability"], "Ability": {"cooldown": 60}}
ABILITY_TWO = {
    "_order": ["Passive Ability", "Vine Crush"],
    "Passive Ability": {"cooldown": 0},
    "Vine Crush": {"cooldown": 30},
}


def count(connection: sqlite3.Connection, table: str) -> int:
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def projectile_row(connection: sqlite3.Connection, attack: str, name: str) -> sqlite3.Row:
    return connection.execute(
        "SELECT p.* FROM projectiles p JOIN attacks a ON a.id = p.attack_id"
        " WHERE a.name = ? AND p.name = ?",
        (attack, name),
    ).fetchone()


def cooldown(connection: sqlite3.Connection) -> Any:
    return connection.execute("SELECT ability_cooldown FROM upgrades").fetchone()[0]


def test_load_tower_stores_attacks_and_projectiles(database) -> None:
    assert load_tower(database, "Ninja Monkey", {"_003": ninja_003()}, "Primary") == 1
    assert count(database, "attacks") == 2
    assert count(database, "projectiles") == 4
    flash = projectile_row(database, "Attack", "Flash Bomb")
    assert (flash["damage"], flash["unlimited_damage"]) == (None, 0)
    row = database.execute("SELECT ability_cooldown, projectile_damage FROM upgrades").fetchone()
    assert (row[0], row[1]) == (None, None)


def test_load_tower_stores_values_and_order(database) -> None:
    load_tower(database, "Ninja Monkey", {"_003": ninja_003()}, "Primary")
    rows = database.execute(
        "SELECT a.attack_index, a.name, a.rate, p.projectile_index, p.name AS pname, p.damage,"
        " p.pierce, p.count, d.name AS damage_type, p.can_hit_camo"
        " FROM attacks a JOIN projectiles p ON p.attack_id = a.id"
        " JOIN damage_types d ON d.id = p.damage_type_id"
        " ORDER BY a.attack_index, p.projectile_index"
    ).fetchall()
    assert [(r[0], r[1], r[2], r[3], r[4]) for r in rows] == [
        (0, "Attack", 0.62, 0, "Flash Bomb"),
        (0, "Attack", 0.62, 1, "Explosion"),
        (0, "Attack", 0.62, 2, "Projectile"),
        (1, "Caltrops", 3.9, 0, "Projectile"),
    ]
    assert [(r["damage"], r["pierce"], r["count"]) for r in rows] == [
        (None, 1, None),
        (3, 30, None),
        (1, 4, 1),
        (1, 6, None),
    ]
    assert [(r["damage_type"], r["can_hit_camo"]) for r in rows] == [
        ("Normal", 1),
        ("Normal", 1),
        ("Sharp", 1),
        ("Sharp", 1),
    ]


def test_load_tower_stores_moab_fields(database) -> None:
    stats = ninja_003()
    projectile = stats["attacks"]["Attack"]["projectiles"]["Explosion"]
    projectile.update({"damageModifierForMoabs": 10, "filterOutNonMoabs": True})
    load_tower(database, "Ninja Monkey", {"_003": stats}, "Primary")
    row = projectile_row(database, "Attack", "Explosion")
    assert (row["moab_bonus_damage"], row["moab_only"]) == (10, 1)
    assert projectile_row(database, "Attack", "Projectile")["moab_only"] == 0


def test_load_tower_reload_keeps_attack_counts(database) -> None:
    for _ in range(2):
        load_tower(database, "Ninja Monkey", {"_003": ninja_003()}, "Primary")
    assert (count(database, "attacks"), count(database, "projectiles")) == (2, 4)


def test_load_tower_reload_removes_stale_attacks(database) -> None:
    load_tower(database, "Ninja Monkey", {"_003": ninja_003()}, "Primary")
    smaller = ninja_003()
    smaller["attacks"]["_order"].remove("Caltrops")
    load_tower(database, "Ninja Monkey", {"_003": smaller}, "Primary")
    assert (count(database, "attacks"), count(database, "projectiles")) == (1, 3)


def test_load_tower_reload_leaves_other_towers(database) -> None:
    load_tower(database, "Ninja Monkey", {"_003": ninja_003()}, "Primary")
    load_tower(database, "Druid", {"_030": druid_030()})
    load_tower(database, "Ninja Monkey", {"_003": ninja_003()}, "Primary")
    assert count(database, "attacks") == 4


def test_load_tower_one_ability(database) -> None:
    stats = ninja_003() | {"abilities": ABILITY_ONE}
    load_tower(database, "Ninja Monkey", {"_003": stats}, "Primary")
    assert cooldown(database) == 60.0


def test_load_tower_two_abilities_keeps_first(database) -> None:
    stats = ninja_003() | {"abilities": ABILITY_TWO}
    load_tower(database, "Ninja Monkey", {"_003": stats}, "Primary")
    assert cooldown(database) == 0.0


def test_load_tower_sentinel_pierce_only(database) -> None:
    load_tower(database, "Druid", {"_400": druid_400()})
    row = projectile_row(database, "Ball Lightning", "Spawning projectile")
    assert (row["damage"], row["pierce"]) == (0.0, None)
    assert (row["unlimited_pierce"], row["unlimited_damage"]) == (1, 0)


def test_load_tower_sentinel_damage_and_pierce(database) -> None:
    load_tower(database, "Druid", {"_030": druid_030()})
    row = projectile_row(database, "Vine", "Collidable")
    assert (row["damage"], row["pierce"]) == (None, None)
    assert (row["unlimited_damage"], row["unlimited_pierce"]) == (1, 1)
    sql = "SELECT COUNT(*) FROM projectiles WHERE damage = ? OR pierce = ?"
    assert database.execute(sql, (UNLIMITED, UNLIMITED)).fetchone()[0] == 0


def test_load_tower_attack_without_projectiles(database) -> None:
    assert load_tower(database, "Alchemist", {"_220": alchemist_220()}) == 1
    attack = database.execute("SELECT name, rate FROM attacks").fetchone()
    assert (attack["name"], attack["rate"]) == ("Acidic Mixture Dip", 10.0)
    assert count(database, "projectiles") == 0
    assert database.execute("SELECT projectile_damage FROM upgrades").fetchone()[0] is None


def test_load_tower_attackless_upgrade_has_no_rows(database) -> None:
    load_tower(database, "Ninja Monkey", {"_000": {"range": 50}}, "Primary")
    assert (count(database, "upgrades"), count(database, "attacks")) == (1, 0)


def test_load_tower_failure_rolls_back_attacks(database) -> None:
    bad = {"_003": ninja_003(), "_bad": ninja_003()}
    bad["_003"]["attacks"]["Attack"]["projectiles"]["Explosion"]["damage"] = -1
    with pytest.raises(sqlite3.Error):
        load_tower(database, "Ninja Monkey", bad, "Primary")
    assert (count(database, "attacks"), count(database, "projectiles")) == (0, 0)


def test_deleting_upgrades_cascades_after_load(database) -> None:
    load_tower(database, "Ninja Monkey", {"_003": ninja_003()}, "Primary")
    database.execute("DELETE FROM upgrades")
    assert (count(database, "attacks"), count(database, "projectiles")) == (0, 0)


def test_summary_columns_match_first_attack_and_projectile(database) -> None:
    resolved = {"_030": druid_030(), "_400": druid_400(), "_003": ninja_003()}
    load_tower(database, "Druid", resolved)
    rows = database.execute(
        "SELECT u.attack_rate, u.projectile_damage, a.rate, p.damage FROM upgrades u"
        " JOIN attacks a ON a.upgrade_id = u.id AND a.attack_index = 0"
        " LEFT JOIN projectiles p ON p.attack_id = a.id AND p.projectile_index = 0"
    ).fetchall()
    assert len(rows) == 3
    for row in rows:
        assert row["attack_rate"] == row["rate"]
        assert row["projectile_damage"] == row["damage"]


damage_values = st.one_of(st.none(), st.integers(0, 50), st.just(UNLIMITED))


@settings(max_examples=40, deadline=None)
@given(
    shapes=st.lists(
        st.lists(st.tuples(damage_values, damage_values), max_size=3), min_size=1, max_size=3
    )
)
def test_reload_is_idempotent_and_counts_match(shapes) -> None:
    from btd6.db import connect
    from btd6.db.seed import initialize_database

    attacks = []
    for attack_number, projectiles in enumerate(shapes):
        built = {}
        for number, (damage, pierce) in enumerate(projectiles):
            fields = {k: v for k, v in (("damage", damage), ("pierce", pierce)) if v is not None}
            built[f"P{number}"] = fields
        attacks.append(make_attack(f"A{attack_number}", 1.0, built))
    resolved = {"_000": make_stats(*attacks)}
    connection = connect(":memory:")
    initialize_database(connection)
    load_tower(connection, "Druid", copy.deepcopy(resolved))
    first = (count(connection, "attacks"), count(connection, "projectiles"))
    load_tower(connection, "Druid", copy.deepcopy(resolved))
    assert (count(connection, "attacks"), count(connection, "projectiles")) == first
    assert first == (len(shapes), sum(len(shape) for shape in shapes))
    sql = "SELECT COUNT(*) FROM projectiles WHERE damage = ? OR pierce = ?"
    assert connection.execute(sql, (UNLIMITED, UNLIMITED)).fetchone()[0] == 0
    connection.close()
