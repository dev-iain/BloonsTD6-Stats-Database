from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6 import recommend as recommend_module
from tests.factories import UpgradeRowFactory
from tests.recommend_fixture import make_threats

ROUND_ONE_DENSITY = 0.0457


@pytest.mark.parametrize(
    ("pierce", "range_value", "density", "expected"),
    [
        (40, 20, ROUND_ONE_DENSITY, 40 * ROUND_ONE_DENSITY),
        (2, 40, ROUND_ONE_DENSITY, 2),
        (40, 20, 0.0, 1.0),
        (40, 20, 0.01, 1.0),
        (40, 20, 0.0251, 40 * 0.0251),
        (4, 20, 0.1, 4),
        (4, 20, 0.2, 4),
        (0.5, 20, 0.0, 0.5),
        (40, None, ROUND_ONE_DENSITY, 40),
        (40, math.nan, ROUND_ONE_DENSITY, 40),
        (40, 20, None, 40),
        (40, None, None, 40),
        (None, 20, ROUND_ONE_DENSITY, None),
        (math.nan, 20, ROUND_ONE_DENSITY, None),
        (None, None, None, None),
    ],
    ids=[
        "ice_monkey_round_one",
        "ninja_monkey_round_one",
        "no_crowd_floors_at_one",
        "small_crowd_floors_at_one",
        "crowd_just_above_floor",
        "crowd_equals_pierce",
        "crowd_above_pierce",
        "pierce_below_floor",
        "null_range",
        "nan_range",
        "none_density",
        "null_range_and_density",
        "null_pierce",
        "nan_pierce",
        "all_missing",
    ],
)
def test_effective_pierce(
    pierce: float | None, range_value: float | None, density: float | None, expected: float | None
) -> None:
    result = recommend_module.effective_pierce(pierce, range_value, density)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected, rel=1e-6)


@given(
    pierce=st.floats(0.0, 1000.0),
    range_value=st.floats(0.0, 500.0),
    density=st.floats(0.0, 5.0),
)
def test_effective_pierce_never_exceeds_pierce_and_keeps_floor(
    pierce: float, range_value: float, density: float
) -> None:
    result = recommend_module.effective_pierce(pierce, range_value, density)
    assert result <= pierce
    assert result >= min(pierce, 1.0)


@given(
    pierce=st.floats(1.0, 1000.0),
    range_value=st.floats(0.0, 500.0),
    smaller=st.floats(0.0, 2.0),
    extra=st.floats(0.0, 2.0),
)
def test_effective_pierce_grows_with_density(
    pierce: float, range_value: float, smaller: float, extra: float
) -> None:
    sparse_pierce = recommend_module.effective_pierce(pierce, range_value, smaller)
    dense_pierce = recommend_module.effective_pierce(pierce, range_value, smaller + extra)
    assert sparse_pierce <= dense_pierce + 1e-9


def upgrade_row(**flags: bool) -> dict:
    return UpgradeRowFactory.build(**flags)


@pytest.mark.parametrize(
    ("threats", "row", "expected"),
    [
        (make_threats(), upgrade_row(), ()),
        (make_threats(), upgrade_row(can_hit_camo=False, can_pop_lead=False), ()),
        (make_threats(camo_share=0.2), upgrade_row(can_hit_camo=False), ("camo",)),
        (make_threats(camo_share=0.2), upgrade_row(can_hit_camo=True), ()),
        (make_threats(camo_share=0.001), upgrade_row(can_hit_camo=False), ("camo",)),
        (make_threats(lead=0.0499), upgrade_row(can_pop_lead=False), ()),
        (make_threats(lead=0.05), upgrade_row(can_pop_lead=False), ("lead",)),
        (make_threats(lead=0.12), upgrade_row(can_pop_lead=True), ()),
        (
            make_threats(camo_share=0.3, lead=0.1, black=0.2),
            upgrade_row(can_hit_camo=False, can_pop_lead=False, can_pop_black=False),
            ("camo", "lead", "black"),
        ),
        (
            make_threats(frozen=0.5, glass=0.5, lead=0.5),
            upgrade_row(can_pop_lead=False, can_pop_glass=False, can_pop_frozen=False),
            ("lead", "glass", "frozen"),
        ),
        (
            make_threats(camo_share=0.3, lead=0.1),
            upgrade_row(can_hit_camo=True, can_pop_lead=False),
            ("lead",),
        ),
    ],
    ids=[
        "no_needs",
        "no_needs_unmet_flags_ignored",
        "camo_unmet",
        "camo_met",
        "camo_tiny_share_still_needed",
        "lead_below_threshold",
        "lead_at_threshold",
        "lead_met",
        "camo_lead_black_in_order",
        "lead_glass_frozen_in_property_order",
        "only_lead_unmet",
    ],
)
def test_unmet_needs(threats: object, row: dict, expected: tuple[str, ...]) -> None:
    assert recommend_module.unmet_needs(row, threats) == expected
