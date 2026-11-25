from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6 import threats as threats_module
from btd6.threats import round_threats
from tests.factories import RoundThreatsFactory
from tests.rounds_fixture import build_rounds_db
from tests.test_threats import MIXED_ROUND, threats_for

ROUND_ONE_SETUP = (
    "UPDATE round_groups SET duration = 17.5125 WHERE round = 1",
    "UPDATE bloons SET speed = 25 WHERE name = 'Red'",
)
MIXED_SETUP = (
    "UPDATE round_groups SET duration = 10 WHERE round = 3",
    "UPDATE bloons SET speed = 25 WHERE name IN ('Red', 'Lead')",
    "UPDATE bloons SET speed = 50 WHERE name = 'Blue'",
)
RED_DENSITY = (5 / 10) / 25
BLUE_DENSITY = (3 / 10) / 50
LEAD_DENSITY = (2 / 10) / 25


def mixed_density(weighted: dict[str, tuple[int, float]]) -> float:
    total = sum(rbe for rbe, _ in weighted.values())
    return sum(rbe * density for rbe, density in weighted.values()) / total


ALL_GROUPS = {
    "Red": (5, RED_DENSITY),
    "Blue": (6, BLUE_DENSITY),
    "Lead": (46, LEAD_DENSITY),
}


def test_min_group_seconds() -> None:
    assert threats_module.MIN_GROUP_SECONDS == 1.0


def test_round_threats_crowd_density_defaults_to_none() -> None:
    assert RoundThreatsFactory.build().crowd_density is None
    assert RoundThreatsFactory.build(crowd_density=0.25).crowd_density == 0.25


def test_round_threats_crowd_density_round_one() -> None:
    result = threats_for({}, 1, *ROUND_ONE_SETUP)
    assert result.crowd_density == pytest.approx(0.045682, abs=1e-6)
    assert result.crowd_density == pytest.approx((20 / 17.5125) / 25)


def test_round_threats_crowd_density_rbe_weighting() -> None:
    result = threats_for(MIXED_ROUND, 3, *MIXED_SETUP)
    assert result.crowd_density == pytest.approx(mixed_density(ALL_GROUPS))
    assert result.crowd_density != pytest.approx((RED_DENSITY + BLUE_DENSITY + LEAD_DENSITY) / 3)


@pytest.mark.parametrize(
    ("duration", "expected"),
    [(0.0, 0.04), (0.5, 0.04), (1.0, 0.04), (2.0, 0.02)],
)
def test_round_threats_crowd_density_duration_clamp(duration: float, expected: float) -> None:
    result = threats_for(
        {40: [("Moab", 1, False)]},
        40,
        f"UPDATE round_groups SET duration = {duration} WHERE round = 40",
        "UPDATE bloons SET speed = 25 WHERE name = 'Moab'",
    )
    assert result.crowd_density == pytest.approx(expected)


@pytest.mark.parametrize("bad_speed", ["NULL", "0"])
def test_round_threats_crowd_density_leaves_out_unusable_speed(bad_speed: str) -> None:
    result = threats_for(
        MIXED_ROUND, 3, *MIXED_SETUP, f"UPDATE bloons SET speed = {bad_speed} WHERE name = 'Blue'"
    )
    expected = mixed_density({"Red": ALL_GROUPS["Red"], "Lead": ALL_GROUPS["Lead"]})
    assert result.crowd_density == pytest.approx(expected)
    assert result.total_rbe == 57


def test_round_threats_crowd_density_leaves_out_null_rbe() -> None:
    result = threats_for(
        MIXED_ROUND, 3, *MIXED_SETUP, "UPDATE bloons SET rbe = NULL WHERE name = 'Blue'"
    )
    expected = mixed_density({"Red": ALL_GROUPS["Red"], "Lead": ALL_GROUPS["Lead"]})
    assert result.crowd_density == pytest.approx(expected)


def test_round_threats_crowd_density_no_speeds_is_none() -> None:
    assert threats_for(MIXED_ROUND, 3).crowd_density is None


def test_round_threats_crowd_density_only_unknown_group_is_none() -> None:
    result = threats_for({}, 27, "UPDATE bloons SET speed = 25", "UPDATE bloons SET rbe = NULL")
    assert result.crowd_density is None


def test_round_threats_crowd_density_empty_round_is_none() -> None:
    connection = build_rounds_db()
    connection.execute("DELETE FROM round_groups WHERE round = 5")
    assert round_threats(connection, 5).crowd_density is None


@given(
    speeds=st.lists(st.floats(1.0, 200.0), min_size=3, max_size=3),
    durations=st.lists(st.floats(0.0, 60.0), min_size=3, max_size=3),
)
def test_round_threats_crowd_density_between_group_densities(
    speeds: list[float], durations: list[float]
) -> None:
    connection = build_rounds_db({3: [("Red", 5, False), ("Blue", 3, False), ("Lead", 2, False)]})
    for name, speed in zip(("Red", "Blue", "Lead"), speeds, strict=True):
        connection.execute("UPDATE bloons SET speed = ? WHERE name = ?", (speed, name))
    for index, duration in enumerate(durations):
        connection.execute(
            "UPDATE round_groups SET duration = ? WHERE round = 3 AND group_index = ?",
            (duration, index),
        )
    counts = (5, 3, 2)
    densities = [
        (count / max(duration, threats_module.MIN_GROUP_SECONDS)) / speed
        for count, duration, speed in zip(counts, durations, speeds, strict=True)
    ]
    result = round_threats(connection, 3).crowd_density
    assert min(densities) - 1e-12 <= result <= max(densities) + 1e-12
