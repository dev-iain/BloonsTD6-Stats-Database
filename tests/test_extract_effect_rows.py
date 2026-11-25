from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.etl.extract import extract_attack_rows, extract_effect_rows, extract_projectile_row
from tests.factories import EffectFactory, effect_container, make_attack, make_stats

GLUE_ROW = {
    "effect_index": 0,
    "name": "Damage over time",
    "damage": 1,
    "tick_interval": 2,
    "lifespan": 11,
    "trigger_immediate": False,
    "moab_bonus_damage": None,
    "moab_only": False,
    "damage_type": "Acid",
}


def single(**fields: Any) -> dict[str, Any]:
    return effect_container(("Damage over time", EffectFactory(**fields)))


def without(key: str) -> dict[str, Any]:
    effect = EffectFactory()
    del effect[key]
    return effect_container(("Damage over time", effect))


def test_extract_effect_rows_all_base() -> None:
    assert extract_effect_rows(single()) == [GLUE_ROW]


@pytest.mark.parametrize("effects", [{}, {"_order": []}], ids=["missing_order", "empty_order"])
def test_extract_effect_rows_empty_container(effects: dict[str, Any]) -> None:
    assert extract_effect_rows(effects) == []


def test_extract_effect_rows_skips_effect_without_damage() -> None:
    freeze = {"lifespan": 2, "interval": 1}
    assert extract_effect_rows(effect_container(("Freeze", freeze))) == []


@pytest.mark.parametrize(
    "fields",
    [{"damage": 0}, {"damage": -3}, {"damage": "lots"}, {"interval": 0}, {"interval": -1}],
    ids=["zero_damage", "negative_damage", "text_damage", "zero_interval", "negative_interval"],
)
def test_extract_effect_rows_skips_unusable_numbers(fields: dict[str, Any]) -> None:
    assert extract_effect_rows(single(**fields)) == []


def test_extract_effect_rows_skips_missing_interval() -> None:
    assert extract_effect_rows(without("interval")) == []


def test_extract_effect_rows_missing_lifespan_is_zero() -> None:
    assert extract_effect_rows(without("lifespan"))[0]["lifespan"] == 0


def test_extract_effect_rows_trigger_immediate_true() -> None:
    assert extract_effect_rows(single(triggerImmediate=True))[0]["trigger_immediate"] is True


def test_extract_effect_rows_missing_trigger_immediate_is_false() -> None:
    assert extract_effect_rows(without("triggerImmediate"))[0]["trigger_immediate"] is False


def test_extract_effect_rows_moab_bonus() -> None:
    assert extract_effect_rows(single(damageModifierForMoabs=3))[0]["moab_bonus_damage"] == 3


def test_extract_effect_rows_moab_only() -> None:
    assert extract_effect_rows(single(filterOutNonMoabs=True))[0]["moab_only"] is True


@pytest.mark.parametrize(
    ("mask", "expected"),
    [(64, "Acid"), (0, "Normal"), (2, "Explosion"), (73, "Energy"), (3, "Unknown")],
)
def test_extract_effect_rows_damage_type_from_own_mask(mask: int, expected: str) -> None:
    assert extract_effect_rows(single(immuneBloonProperties=mask))[0]["damage_type"] == expected


def test_extract_effect_rows_missing_mask_is_normal() -> None:
    assert extract_effect_rows(without("immuneBloonProperties"))[0]["damage_type"] == "Normal"


def test_extract_effect_rows_index_is_position_in_order() -> None:
    effects = effect_container(
        ("Freeze", {"lifespan": 2}),
        ("Zero", EffectFactory(damage=0)),
        ("Laser Shock", EffectFactory(damage=5, interval=0.5, lifespan=2)),
        ("Super Glue damage", EffectFactory(damage=30, interval=1, lifespan=0.95)),
    )
    rows = extract_effect_rows(effects)
    assert [(row["effect_index"], row["name"]) for row in rows] == [
        (2, "Laser Shock"),
        (3, "Super Glue damage"),
    ]


def test_extract_effect_rows_ninja_damage_to_target() -> None:
    effects = effect_container(
        ("Damage to target", EffectFactory(damage=450, interval=2.95, lifespan=3))
    )
    row = extract_effect_rows(effects)[0]
    assert (row["damage"], row["tick_interval"], row["lifespan"]) == (450, 2.95, 3)


def test_projectile_row_has_effects_key() -> None:
    row = extract_projectile_row(0, "Projectile", {"effects": single()})
    assert row["effects"] == [GLUE_ROW]


@pytest.mark.parametrize("projectile", [{}, {"effects": {}}, {"damage": 3}])
def test_projectile_row_without_effects_is_empty_list(projectile: dict[str, Any]) -> None:
    assert extract_projectile_row(0, "Projectile", projectile)["effects"] == []


def test_attack_rows_carry_effects_per_projectile() -> None:
    projectiles = {"Plain": {"damage": 1}, "Glue": {"effects": single()}}
    rows = extract_attack_rows(make_stats(make_attack("Attack", 1, projectiles)))
    assert [proj["effects"] for proj in rows[0]["projectiles"]] == [[], [GLUE_ROW]]


EFFECT_FIELDS = st.fixed_dictionaries(
    {
        "damage": st.one_of(st.integers(-2, 50), st.just("x")),
        "interval": st.one_of(st.integers(-1, 5), st.floats(0.1, 4), st.none()),
        "lifespan": st.floats(0, 20),
    }
)


@settings(max_examples=60, deadline=None)
@given(st.lists(EFFECT_FIELDS, max_size=6))
def test_extract_effect_rows_only_positive_numbers_and_ordered(fields_list: list[dict]) -> None:
    named = []
    for position, fields in enumerate(fields_list):
        effect = EffectFactory(**{key: value for key, value in fields.items() if value is not None})
        if fields["interval"] is None:
            del effect["interval"]
        named.append((f"Effect {position}", effect))
    rows = extract_effect_rows(effect_container(*named))
    indices = [row["effect_index"] for row in rows]
    assert indices == sorted(set(indices))
    assert all(index < len(named) for index in indices)
    assert all(row["damage"] > 0 and row["tick_interval"] > 0 for row in rows)
    assert all(row["lifespan"] >= 0 for row in rows)
