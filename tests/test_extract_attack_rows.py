from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from btd6.etl.extract import extract_attack_rows, extract_row
from btd6.etl.fetch import PROJECT_ROOT
from tests.factories import (
    UNLIMITED,
    alchemist_220,
    druid_030,
    druid_400,
    make_attack,
    make_stats,
    ninja_003,
    wizard_005,
    wizard_400,
)

FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
MULTI_ATTACK_COUNTS = {"wizard": 30, "ninja": 16, "alchemist": 32, "druid": 26}


def projectile_values(rows: list[dict[str, Any]], key: str) -> list[Any]:
    return [proj[key] for row in rows for proj in row["projectiles"]]


def edit(stats: dict[str, Any], attack: str, projectile: str, **fields: Any) -> dict[str, Any]:
    edited = copy.deepcopy(stats)
    edited["attacks"][attack]["projectiles"][projectile].update(fields)
    return edited


def find(rows: list[dict[str, Any]], attack: str, projectile: str) -> dict[str, Any]:
    attack_row = next(row for row in rows if row["name"] == attack)
    return next(proj for proj in attack_row["projectiles"] if proj["name"] == projectile)


def test_extract_attack_rows_several_attacks() -> None:
    rows = extract_attack_rows(ninja_003())
    assert [(row["attack_index"], row["name"], row["rate"]) for row in rows] == [
        (0, "Attack", 0.62),
        (1, "Caltrops", 3.9),
    ]
    assert [proj["projectile_index"] for row in rows for proj in row["projectiles"]] == [0, 1, 2, 0]
    flash = find(rows, "Attack", "Flash Bomb")
    assert flash["damage"] is None
    assert (flash["pierce"], flash["speed"], flash["radius"], flash["lifespan"]) == (
        1,
        300,
        5,
        0.57,
    )
    assert (flash["damage_type"], flash["can_hit_camo"]) == ("Normal", True)
    assert find(rows, "Attack", "Explosion")["damage"] == 3
    assert find(rows, "Attack", "Explosion")["pierce"] == 30
    projectile = find(rows, "Attack", "Projectile")
    assert (projectile["damage"], projectile["pierce"], projectile["count"]) == (1, 4, 1)
    assert projectile["damage_type"] == "Sharp"
    caltrops = find(rows, "Caltrops", "Projectile")
    assert (caltrops["damage"], caltrops["pierce"], caltrops["lifespan"]) == (1, 6, 35)
    assert caltrops["damage_type"] == "Sharp"
    assert not any(projectile_values(rows, "unlimited_damage"))
    assert not any(projectile_values(rows, "unlimited_pierce"))
    assert not any(projectile_values(rows, "moab_only"))
    assert projectile_values(rows, "moab_bonus_damage") == [None] * 4


def test_extract_attack_rows_count_is_none_when_omitted() -> None:
    rows = extract_attack_rows(ninja_003())
    assert find(rows, "Attack", "Explosion")["count"] is None


def test_extract_attack_rows_one_attack() -> None:
    stats = ninja_003()
    stats["attacks"]["_order"].remove("Caltrops")
    rows = extract_attack_rows(stats)
    assert [row["name"] for row in rows] == ["Attack"]


def test_extract_attack_rows_no_attacks() -> None:
    assert extract_attack_rows({"range": 50}) == []


def test_extract_attack_rows_attack_without_projectiles() -> None:
    assert extract_attack_rows(alchemist_220()) == [
        {"attack_index": 0, "name": "Acidic Mixture Dip", "rate": 10, "projectiles": []}
    ]


def test_extract_attack_rows_one_projectile_each() -> None:
    stats = ninja_003()
    stats["attacks"]["Attack"]["projectiles"]["_order"] = ["Flash Bomb"]
    rows = extract_attack_rows(stats)
    assert [len(row["projectiles"]) for row in rows] == [1, 1]


def test_extract_attack_rows_all_damage_present() -> None:
    rows = extract_attack_rows(edit(ninja_003(), "Attack", "Flash Bomb", damage=2))
    assert projectile_values(rows, "damage") == [2, 3, 1, 1]


def test_extract_attack_rows_sentinel_pierce_only() -> None:
    stats = edit(ninja_003(), "Caltrops", "Projectile", pierce=UNLIMITED)
    caltrops = find(extract_attack_rows(stats), "Caltrops", "Projectile")
    assert caltrops["pierce"] is None
    assert caltrops["unlimited_pierce"] is True
    assert caltrops["damage"] == 1
    assert caltrops["unlimited_damage"] is False


def test_extract_attack_rows_sentinel_damage_and_pierce() -> None:
    stats = edit(ninja_003(), "Caltrops", "Projectile", damage=UNLIMITED, pierce=UNLIMITED)
    rows = extract_attack_rows(stats)
    caltrops = find(rows, "Caltrops", "Projectile")
    assert (caltrops["damage"], caltrops["pierce"]) == (None, None)
    assert (caltrops["unlimited_damage"], caltrops["unlimited_pierce"]) == (True, True)
    flash = find(rows, "Attack", "Flash Bomb")
    assert (flash["damage"], flash["unlimited_damage"]) == (None, False)


def test_extract_attack_rows_moab_bonus() -> None:
    rows = extract_attack_rows(edit(ninja_003(), "Attack", "Explosion", damageModifierForMoabs=10))
    assert projectile_values(rows, "moab_bonus_damage") == [None, 10, None, None]


def test_extract_attack_rows_moab_only() -> None:
    rows = extract_attack_rows(edit(ninja_003(), "Caltrops", "Projectile", filterOutNonMoabs=True))
    assert projectile_values(rows, "moab_only") == [False, False, False, True]


def test_extract_attack_rows_invisible_filter_gives_no_camo() -> None:
    rows = extract_attack_rows(edit(ninja_003(), "Caltrops", "Projectile", filterInvisible=True))
    assert find(rows, "Caltrops", "Projectile")["can_hit_camo"] is False


def test_extract_attack_rows_wizard_005() -> None:
    rows = extract_attack_rows(wizard_005())
    assert len(rows) == 4
    assert max(len(row["projectiles"]) for row in rows) == 2
    assert find(rows, "MOAB", "MOAB")["damage"] == 40
    assert find(rows, "MOAB", "BFB")["damage"] == 100
    shimmer = find(rows, "Shimmer", "Projectile")
    assert (shimmer["damage"], shimmer["pierce"]) == (None, 500)


def test_extract_attack_rows_druid_030() -> None:
    rows = extract_attack_rows(druid_030())
    assert len(rows) == 2
    collidable = find(rows, "Vine", "Collidable")
    assert (collidable["damage"], collidable["pierce"]) == (None, None)
    assert (collidable["unlimited_damage"], collidable["unlimited_pierce"]) == (True, True)
    vine = find(rows, "Vine", "Projectile")
    assert (vine["damage"], vine["pierce"]) == (1, 20)


def test_extract_attack_rows_druid_400() -> None:
    spawning = find(extract_attack_rows(druid_400()), "Ball Lightning", "Spawning projectile")
    assert spawning["damage"] == 0
    assert spawning["pierce"] is None
    assert (spawning["unlimited_pierce"], spawning["unlimited_damage"]) == (True, False)


def test_extract_attack_rows_wizard_400_moab_bonus() -> None:
    assert (
        find(extract_attack_rows(wizard_400()), "Attack", "Projectile")["moab_bonus_damage"] == 10
    )


def test_extract_attack_rows_does_not_mutate_input() -> None:
    stats = druid_030()
    snapshot = copy.deepcopy(stats)
    extract_attack_rows(stats)
    assert stats == snapshot


@pytest.mark.parametrize("field", ["damage", "pierce"])
def test_extract_row_sentinel_becomes_none(field) -> None:
    stats = druid_030()
    stats["attacks"]["Vine"]["projectiles"]["_order"] = ["Collidable"]
    stats["attacks"]["_order"] = ["Vine"]
    assert extract_row("_030", stats)[f"projectile_{field}"] is None


def test_extract_row_sentinel_agrees_with_attack_rows() -> None:
    stats = make_stats(
        make_attack("Vine", 2.6, {"Collidable": {"damage": UNLIMITED, "pierce": UNLIMITED}})
    )
    row = extract_row("_030", stats)
    projectile = extract_attack_rows(stats)[0]["projectiles"][0]
    assert (row["projectile_damage"], row["projectile_pierce"]) == (
        projectile["damage"],
        projectile["pierce"],
    )


def test_extract_row_summary_unchanged_for_ninja() -> None:
    row = extract_row("_003", ninja_003())
    assert row["projectile_damage"] is None
    assert row["attack_rate"] == 0.62


def load_resolved(name: str) -> dict[str, Any]:
    path = FIXTURES / f"{name}_resolved.json"
    if not path.exists():
        pytest.skip(f"{path.name} not present (resolved wiki JSON)")
    return json.loads(path.read_text())


def test_super_monkey_every_upgrade_has_one_attack_one_projectile(super_monkey_resolved) -> None:
    for stats in super_monkey_resolved.values():
        rows = extract_attack_rows(stats)
        assert len(rows) == 1
        assert len(rows[0]["projectiles"]) == 1


@pytest.mark.parametrize(("tower", "expected"), MULTI_ATTACK_COUNTS.items())
def test_upgrades_with_more_than_one_attack(tower, expected) -> None:
    resolved = load_resolved(tower)
    assert len(resolved) == 64
    assert sum(len(extract_attack_rows(stats)) > 1 for stats in resolved.values()) == expected


@pytest.mark.parametrize("tower", MULTI_ATTACK_COUNTS)
def test_extracted_counts_match_order_lists(tower) -> None:
    for stats in load_resolved(tower).values():
        rows = extract_attack_rows(stats)
        assert len(rows) == len(stats["attacks"]["_order"])


@pytest.mark.parametrize("tower", MULTI_ATTACK_COUNTS)
def test_no_sentinel_survives_extraction(tower) -> None:
    for stats in load_resolved(tower).values():
        rows = extract_attack_rows(stats)
        assert UNLIMITED not in projectile_values(rows, "damage")
        assert UNLIMITED not in projectile_values(rows, "pierce")


@pytest.mark.parametrize("tower", MULTI_ATTACK_COUNTS)
def test_summary_agrees_with_first_attack_and_projectile(tower) -> None:
    for code, stats in load_resolved(tower).items():
        summary = extract_row(code, stats)
        first = extract_attack_rows(stats)[0]
        assert summary["attack_rate"] == first["rate"]
        if first["projectiles"]:
            assert summary["projectile_damage"] == first["projectiles"][0]["damage"]
