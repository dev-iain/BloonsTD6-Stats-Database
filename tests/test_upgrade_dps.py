from __future__ import annotations

import copy
import sqlite3
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.db import connect
from btd6.db.loader import load_tower
from btd6.db.seed import initialize_database
from btd6.ranking import all_upgrade_dps, upgrade_dps, upgrade_moab_dps
from tests.factories import (
    UNLIMITED,
    alchemist_220,
    druid_030,
    druid_400,
    make_attack,
    make_stats,
    ninja_003,
    projectile_of,
    stored_upgrade_id,
    wizard_005,
    wizard_400,
)


def figures(connection: sqlite3.Connection, tower: str, path: str) -> tuple[Any, Any]:
    upgrade_id = stored_upgrade_id(connection, tower, path)
    return upgrade_dps(connection, upgrade_id), upgrade_moab_dps(connection, upgrade_id)


def figures_of(
    database: sqlite3.Connection, stats: dict[str, Any], code: str = "_003"
) -> tuple[Any, Any]:
    load_tower(database, "Ninja Monkey", {code: stats}, "Primary")
    return figures(database, "Ninja Monkey", f"{code[1]}-{code[2]}-{code[3]}")


def assert_figures(actual: tuple[Any, Any], expected: tuple[Any, Any]) -> None:
    for value, wanted in zip(actual, expected, strict=True):
        if wanted is None:
            assert value is None
        else:
            assert value == pytest.approx(wanted, rel=1e-5)


def drop_caltrops(stats: dict[str, Any]) -> None:
    stats["attacks"]["_order"].remove("Caltrops")


def empty_attacks(stats: dict[str, Any]) -> None:
    stats["attacks"]["_order"] = []


def caltrops_without_rate(stats: dict[str, Any]) -> None:
    del stats["attacks"]["Caltrops"]["rate"]


def caltrops_zero_rate(stats: dict[str, Any]) -> None:
    stats["attacks"]["Caltrops"]["rate"] = 0


def flash_bomb_damage_two(stats: dict[str, Any]) -> None:
    projectile_of(stats, "Attack", "Flash Bomb")["damage"] = 2


def attack_without_damage(stats: dict[str, Any]) -> None:
    for name in ("Explosion", "Projectile"):
        del projectile_of(stats, "Attack", name)["damage"]


def caltrops_unlimited(stats: dict[str, Any]) -> None:
    projectile_of(stats, "Caltrops", "Projectile")["damage"] = UNLIMITED


def explosion_count_two(stats: dict[str, Any]) -> None:
    projectile_of(stats, "Attack", "Explosion")["count"] = 2


def explosion_moab_bonus(stats: dict[str, Any]) -> None:
    projectile_of(stats, "Attack", "Explosion")["damageModifierForMoabs"] = 10


def caltrops_moab_only(stats: dict[str, Any]) -> None:
    projectile_of(stats, "Caltrops", "Projectile")["filterOutNonMoabs"] = True


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (None, (6.70802, 6.70802)),
        (empty_attacks, (None, None)),
        (drop_caltrops, (6.45161, 6.45161)),
        (caltrops_without_rate, (6.45161, 6.45161)),
        (caltrops_zero_rate, (6.45161, 6.45161)),
        (flash_bomb_damage_two, (9.93383, 9.93383)),
        (attack_without_damage, (0.25641, 0.25641)),
        (caltrops_unlimited, (6.45161, 6.45161)),
        (explosion_count_two, (11.54673, 11.54673)),
        (explosion_moab_bonus, (6.70802, 22.83706)),
        (caltrops_moab_only, (6.45161, 6.70802)),
    ],
    ids=[
        "base_ninja_0_0_3",
        "no_attacks",
        "one_attack",
        "null_rate_skips_attack",
        "zero_rate_skips_attack",
        "all_damage_present",
        "attack_without_damage_skipped",
        "unlimited_damage_excluded",
        "count_multiplies",
        "moab_bonus",
        "moab_only_split",
    ],
)
def test_upgrade_dps_ninja_variants(database, edit, expected) -> None:
    stats = ninja_003()
    if edit is not None:
        edit(stats)
    dps, moab_dps = figures_of(database, stats)
    assert_figures((dps, moab_dps), expected)


def test_ninja_003_dps_uses_explosion_projectile(database) -> None:
    dps, _ = figures_of(database, ninja_003())
    assert dps == pytest.approx(6.7080, rel=1e-5)
    assert dps != pytest.approx(1 / 0.62 + 1 / 3.9, rel=1e-3)


def test_wizard_005_stable_part_without_moab_attack(database) -> None:
    stats = wizard_005()
    stats["attacks"]["_order"].remove("MOAB")
    dps, _ = figures_of(database, stats, "_005")
    assert dps == pytest.approx(1 / 0.275 + 2 / 1.5, rel=1e-5)


def test_wizard_005_moab_and_bfb_are_alternatives(database) -> None:
    """MOAB (40) and BFB (100) are alternatives: DPS takes the smallest, MOAB DPS the largest."""
    dps, moab_dps = figures_of(database, wizard_005(), "_005")
    assert dps == pytest.approx(18.30303, rel=1e-5)
    assert moab_dps == pytest.approx(38.30303, rel=1e-5)


@pytest.mark.parametrize(
    ("maker", "code", "tower", "expected_dps", "expected_moab"),
    [
        (druid_030, "_030", "Druid", 7.65734, 7.65734),
        (druid_400, "_400", "Druid", 6.34980, 6.34980),
        (alchemist_220, "_220", "Alchemist", None, None),
        (wizard_400, "_400", "Wizard Monkey", 21.81818, 58.18182),
    ],
    ids=["druid_0_3_0", "druid_4_0_0", "alchemist_2_2_0", "wizard_4_0_0"],
)
def test_upgrade_dps_real_cases(database, maker, code, tower, expected_dps, expected_moab) -> None:
    load_tower(database, tower, {code: maker()}, "Magic")
    path = f"{code[1]}-{code[2]}-{code[3]}"
    dps, moab_dps = figures(database, tower, path)
    if expected_dps is None:
        assert (dps, moab_dps) == (None, None)
    else:
        assert dps == pytest.approx(expected_dps, rel=1e-5)
        assert moab_dps == pytest.approx(expected_moab, rel=1e-5)


def test_druid_sentinel_projectiles_never_give_infinity(database) -> None:
    load_tower(database, "Druid", {"_030": druid_030(), "_400": druid_400()}, "Magic")
    for path in ("0-3-0", "4-0-0"):
        for value in figures(database, "Druid", path):
            assert value is not None
            assert value < 1000


def test_all_upgrade_dps_matches_per_upgrade_functions(database) -> None:
    load_tower(database, "Ninja Monkey", {"_003": ninja_003()}, "Primary")
    load_tower(database, "Wizard Monkey", {"_005": wizard_005(), "_400": wizard_400()}, "Magic")
    load_tower(database, "Druid", {"_030": druid_030(), "_400": druid_400()}, "Magic")
    load_tower(database, "Alchemist", {"_220": alchemist_220()}, "Magic")
    bulk = all_upgrade_dps(database)
    ids = [row[0] for row in database.execute("SELECT id FROM upgrades")]
    assert set(bulk) == set(ids)
    for upgrade_id in ids:
        single = (upgrade_dps(database, upgrade_id), upgrade_moab_dps(database, upgrade_id))
        assert_figures(bulk[upgrade_id], single)


def test_all_upgrade_dps_empty_database(database) -> None:
    assert all_upgrade_dps(database) == {}


PROJECTILE = st.fixed_dictionaries(
    {},
    optional={
        "damage": st.one_of(st.integers(0, 20), st.just(UNLIMITED)),
        "count": st.integers(1, 5),
        "damageModifierForMoabs": st.integers(0, 20),
        "filterOutNonMoabs": st.booleans(),
        "pierce": st.integers(1, 50),
    },
)
ATTACK = st.tuples(
    st.one_of(st.none(), st.sampled_from([0, 0.3, 1, 2.5])),
    st.lists(PROJECTILE, max_size=3),
)


@settings(max_examples=50, deadline=None)
@given(attacks=st.lists(ATTACK, max_size=4))
def test_dps_is_finite_and_moab_dps_never_lower(attacks) -> None:
    connection = connect(":memory:")
    initialize_database(connection)
    built = [
        make_attack(f"Attack {index}", rate, {f"P{slot}": proj for slot, proj in enumerate(projs)})
        for index, (rate, projs) in enumerate(attacks)
    ]
    stats = make_stats(*copy.deepcopy(built))
    load_tower(connection, "Ninja Monkey", {"_001": stats}, "Primary")
    dps, moab_dps = figures(connection, "Ninja Monkey", "0-0-1")
    connection.close()
    assert (dps is None) or (moab_dps is not None)
    if dps is not None:
        assert 0 <= dps < 1e6
        assert moab_dps >= dps - 1e-9
