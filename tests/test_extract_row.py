from __future__ import annotations

import copy
from typing import Any

from btd6.etl.extract import extract_row
from tests.factories import StatsFactory, UpgradeRowFactory

BASE_CODE = "_100"
BASE_STATS: dict[str, Any] = {
    "range": 50,
    "attacks": {
        "_order": ["a"],
        "a": {
            "rate": 0.045,
            "projectiles": {
                "_order": ["p"],
                "p": {
                    "damage": 1,
                    "pierce": 2,
                    "immuneBloonProperties": 73,
                    "filterInvisible": True,
                },
            },
        },
    },
}
POP_FLAGS = (
    "can_pop_lead",
    "can_pop_black",
    "can_pop_white",
    "can_pop_purple",
    "can_pop_glass",
    "can_pop_frozen",
)


def build_stats(**changes: Any) -> dict[str, Any]:
    """Deep copy of the T1 stats, with top-level keys replaced or removed (None removes)."""
    stats = copy.deepcopy(BASE_STATS)
    for key, value in changes.items():
        if value is None:
            stats.pop(key, None)
        else:
            stats[key] = value
    return stats


def base_projectile(stats: dict[str, Any]) -> dict[str, Any]:
    return stats["attacks"]["a"]["projectiles"]["p"]


def base_row() -> dict[str, Any]:
    return extract_row(BASE_CODE, build_stats())


def with_projectile_changes(**changes: Any) -> dict[str, Any]:
    stats = build_stats()
    base_projectile(stats).update(changes)
    return stats


def without_projectile_key(key: str) -> dict[str, Any]:
    stats = build_stats()
    del base_projectile(stats)[key]
    return stats


def assert_all_pop_flags(row: dict[str, Any], expected: bool) -> None:
    for flag in POP_FLAGS:
        assert row[flag] is expected, flag


def test_extract_row_all_base() -> None:
    """BCC case T1."""
    row = base_row()
    assert len(row) == 19
    assert row["path"] == "1-0-0"
    assert row["range"] == 50
    assert row["attack_rate"] == 0.045
    assert row["projectile_damage"] == 1
    assert row["projectile_pierce"] == 2
    assert row["damage_type"] == "Energy"
    assert row["can_hit_camo"] is False
    for flag in ("can_pop_lead", "can_pop_purple", "can_pop_glass"):
        assert row[flag] is False
    for flag in ("can_pop_black", "can_pop_white", "can_pop_frozen"):
        assert row[flag] is True
    assert row["ability_cooldown"] is None
    assert row["footprint_radius"] is None


def test_extract_row_immunity_absent() -> None:
    """BCC case T2."""
    row = extract_row(BASE_CODE, without_projectile_key("immuneBloonProperties"))
    assert row["damage_type"] == "Normal"
    assert_all_pop_flags(row, True)


def test_extract_row_single_immunity() -> None:
    """BCC case T3."""
    row = extract_row(BASE_CODE, with_projectile_changes(immuneBloonProperties=1))
    assert row["damage_type"] == "Shatter"
    assert row["can_pop_lead"] is False
    for flag in POP_FLAGS[1:]:
        assert row[flag] is True, flag


def test_extract_row_unknown_mask() -> None:
    """BCC case T4."""
    row = extract_row(BASE_CODE, with_projectile_changes(immuneBloonProperties=3))
    assert row["damage_type"] == "Unknown"
    assert_all_pop_flags(row, True)


def test_extract_row_attack_without_projectiles() -> None:
    """BCC case T5."""
    stats = build_stats()
    stats["attacks"]["a"] = {"rate": 0.045}
    row = extract_row(BASE_CODE, stats)
    assert row["attack_rate"] == 0.045
    assert row["projectile_pierce"] is None
    assert row["projectile_damage"] is None
    assert row["damage_type"] == "Normal"
    assert_all_pop_flags(row, True)
    assert row["can_hit_camo"] is True


def test_extract_row_no_attacks() -> None:
    """BCC case T6."""
    row = extract_row(BASE_CODE, build_stats(attacks=None))
    assert row["range"] == 50
    assert row["attack_rate"] is None
    assert row["projectile_pierce"] is None
    assert row["damage_type"] == "Normal"
    assert_all_pop_flags(row, True)
    assert row["can_hit_camo"] is True


def test_extract_row_empty_attack_order() -> None:
    """BCC case T7."""
    row = extract_row(BASE_CODE, build_stats(attacks={"_order": []}))
    assert row["attack_rate"] is None
    assert row["projectile_pierce"] is None
    assert row["can_hit_camo"] is True


def test_extract_row_base_upgrade_code() -> None:
    """BCC case T8."""
    row = extract_row("_000", build_stats())
    assert row["path"] == "0-0-0"
    assert {**row, "path": "1-0-0"} == base_row()


def test_extract_row_multi_digit_code() -> None:
    """BCC case T9."""
    row = extract_row("_023", build_stats())
    assert row["path"] == "0-2-3"
    assert {**row, "path": "1-0-0"} == base_row()


def test_extract_row_filter_invisible_false() -> None:
    """BCC case T10."""
    row = extract_row(BASE_CODE, with_projectile_changes(filterInvisible=False))
    assert row["can_hit_camo"] is True
    assert {**row, "can_hit_camo": False} == base_row()


def test_extract_row_filter_invisible_absent() -> None:
    """BCC case T11."""
    row = extract_row(BASE_CODE, without_projectile_key("filterInvisible"))
    assert row["can_hit_camo"] is True
    assert {**row, "can_hit_camo": False} == base_row()


def test_extract_row_only_first_entries_read() -> None:
    """BCC case T12."""
    stats = build_stats()
    stats["attacks"]["_order"].append("b")
    stats["attacks"]["b"] = {"rate": 5}
    stats["attacks"]["a"]["projectiles"]["_order"].append("q")
    stats["attacks"]["a"]["projectiles"]["q"] = {"pierce": 9}
    row = extract_row(BASE_CODE, stats)
    assert row["attack_rate"] == 0.045
    assert row["projectile_pierce"] == 2
    assert row == base_row()


def test_extract_row_ability_cooldown() -> None:
    """BCC case T13."""
    abilities = {"_order": ["x"], "x": {"cooldown": 30}}
    row = extract_row(BASE_CODE, build_stats(abilities=abilities))
    assert row["ability_cooldown"] == 30
    assert {**row, "ability_cooldown": None} == base_row()


def test_extract_row_ability_without_attacks() -> None:
    """BCC case T14."""
    abilities = {"_order": ["x"], "x": {"cooldown": 30}}
    row = extract_row(BASE_CODE, build_stats(attacks=None, abilities=abilities))
    assert row["ability_cooldown"] == 30
    assert row["attack_rate"] is None


def test_extract_row_matches_factory_row() -> None:
    expected = UpgradeRowFactory(path="1-0-0", range=50, projectile_pierce=2, damage_type="Normal")
    row = extract_row("_100", StatsFactory(mask=0, invisible=False, pierce=2))
    assert row["projectile_pierce"] == expected["projectile_pierce"]
    assert row["can_hit_camo"] is True
    assert row["damage_type"] == expected["damage_type"]
    assert set(row) == set(expected)
