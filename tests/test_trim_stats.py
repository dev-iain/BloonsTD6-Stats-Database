from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from btd6.etl import fetch
from btd6.etl.extract import extract_row
from btd6.etl.fetch import resolve_all_codes, trim_stats, write_resolved_json

PROJECTILE_KEPT_FIELDS = {
    "count": 1,
    "damage": 2,
    "pierce": 3,
    "speed": 40,
    "radius": 5,
    "lifespan": 1.5,
    "immuneBloonProperties": 1,
    "filterInvisible": True,
}
PROJECTILE_JUNK_FIELDS = {"maxPierce": 9, "eject": True, "name": "junk"}
ATTACK_JUNK_FIELDS = {"range": 99, "count": 4, "filterInvisible": True, "targetTypeFirst": True}


def build_projectile(**overrides: Any) -> dict[str, Any]:
    projectile = {**PROJECTILE_KEPT_FIELDS, **PROJECTILE_JUNK_FIELDS}
    projectile.update(overrides)
    return projectile


def build_attack(rate: float = 0.5, projectile_count: int = 1) -> dict[str, Any]:
    names = [f"Proj{index}" for index in range(projectile_count)]
    projectiles: dict[str, Any] = {"_order": names}
    for index, name in enumerate(names):
        projectiles[name] = build_projectile(damage=index + 1)
    return {"rate": rate, "projectiles": projectiles, **ATTACK_JUNK_FIELDS}


def build_stats(attack_count: int = 2, projectile_count: int = 2) -> dict[str, Any]:
    attacks: dict[str, Any] = {"_order": [f"Attack{index}" for index in range(attack_count)]}
    for index in range(attack_count):
        attacks[f"Attack{index}"] = build_attack(
            rate=0.5 + index, projectile_count=projectile_count
        )
    return {
        "range": 40,
        "footprintRadius": 8,
        "placeableOnLand": True,
        "cost": 100,
        "attacks": attacks,
        "abilities": {
            "_order": ["Ability0", "Ability1"],
            "Ability0": {"cooldown": 30, "name": "junk"},
            "Ability1": {"cooldown": 60, "icon": "junk"},
        },
    }


def test_junk_fields_are_dropped() -> None:
    trimmed = trim_stats(build_stats())
    assert "placeableOnLand" not in trimmed
    assert "cost" not in trimmed
    attack = trimmed["attacks"]["Attack0"]
    assert set(attack) == {"rate", "projectiles"}
    projectile = attack["projectiles"]["Proj0"]
    assert set(projectile) == set(PROJECTILE_KEPT_FIELDS)
    assert trimmed["abilities"]["Ability0"] == {"cooldown": 30}


def test_kept_fields_are_preserved_for_every_entry() -> None:
    trimmed = trim_stats(build_stats())
    assert trimmed["range"] == 40
    assert trimmed["footprintRadius"] == 8
    assert trimmed["attacks"]["_order"] == ["Attack0", "Attack1"]
    assert trimmed["attacks"]["Attack1"]["rate"] == 1.5
    assert trimmed["attacks"]["Attack1"]["projectiles"]["_order"] == ["Proj0", "Proj1"]
    second = trimmed["attacks"]["Attack1"]["projectiles"]["Proj1"]
    assert second == {**PROJECTILE_KEPT_FIELDS, "damage": 2}
    assert trimmed["abilities"]["_order"] == ["Ability0", "Ability1"]
    assert trimmed["abilities"]["Ability1"] == {"cooldown": 60}


def test_input_is_not_mutated() -> None:
    stats = build_stats()
    snapshot = copy.deepcopy(stats)
    trim_stats(stats)
    assert stats == snapshot


def test_trim_is_idempotent() -> None:
    once = trim_stats(build_stats())
    assert trim_stats(once) == once


EDGE_CASES = {
    "no_attacks": {"range": 10, "footprintRadius": 2},
    "attack_without_projectiles": {
        "range": 10,
        "attacks": {"_order": ["A"], "A": {"rate": 1, "junk": 1}},
    },
    "empty_attack_order": {"range": 10, "attacks": {"_order": []}},
    "empty_projectile_order": {
        "attacks": {"_order": ["A"], "A": {"rate": 1, "projectiles": {"_order": []}}}
    },
    "no_abilities": {"range": 10, "attacks": {"_order": []}},
    "empty_ability_order": {"abilities": {"_order": []}},
    "empty_stats": {},
}


def expected_edge_result(stats: dict[str, Any]) -> dict[str, Any]:
    expected = copy.deepcopy(stats)
    attack = expected.get("attacks", {}).get("A")
    if attack is not None:
        attack.pop("junk", None)
    return expected


@pytest.mark.parametrize("stats", EDGE_CASES.values(), ids=EDGE_CASES.keys())
def test_edge_cases_do_not_raise_or_add_keys(stats: dict[str, Any]) -> None:
    assert trim_stats(stats) == expected_edge_result(stats)


VARIANTS = {
    "full": build_stats(),
    "single_attack": build_stats(attack_count=1, projectile_count=1),
    "no_attacks": EDGE_CASES["no_attacks"],
    "no_projectiles": EDGE_CASES["attack_without_projectiles"],
    "no_abilities": EDGE_CASES["no_abilities"],
    "empty": EDGE_CASES["empty_stats"],
    "unknown_damage_mask": {
        "attacks": {
            "_order": ["A"],
            "A": {
                "rate": 1,
                "projectiles": {"_order": ["P"], "P": build_projectile(immuneBloonProperties=7)},
            },
        }
    },
}


@pytest.mark.parametrize("stats", VARIANTS.values(), ids=VARIANTS.keys())
def test_extract_row_is_unchanged_by_trimming(stats: dict[str, Any]) -> None:
    assert extract_row("_023", trim_stats(stats)) == extract_row("_023", stats)


def test_write_resolved_json_writes_trimmed_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tower_module = {"_001": build_stats(attack_count=1), "_002": build_stats()}
    monkeypatch.setattr(
        fetch, "fetch_tower_module", lambda _tower_name: copy.deepcopy(tower_module)
    )
    output_path = tmp_path / "out.json"

    returned_path = write_resolved_json("X", json_path=output_path)

    expected = {code: trim_stats(stats) for code, stats in resolve_all_codes(tower_module).items()}
    assert returned_path == output_path
    assert json.loads(output_path.read_text()) == expected
