from __future__ import annotations

import pytest

from btd6.etl.extract import DAMAGE_TYPES, extract_row
from tests.factories import StatsFactory, UpgradeRowFactory


def test_row_keys_match_extract_row() -> None:
    real_row = extract_row("_100", StatsFactory())
    assert list(UpgradeRowFactory()) == list(real_row)


def test_row_overrides_apply() -> None:
    row = UpgradeRowFactory(projectile_pierce=5, can_pop_lead=False)
    assert row["projectile_pierce"] == 5
    assert row["can_pop_lead"] is False
    assert row["can_pop_black"] is True


def test_row_paths_are_unique() -> None:
    paths = [UpgradeRowFactory()["path"] for _ in range(300)]
    assert len(set(paths)) == len(paths)


@pytest.mark.parametrize("mask", sorted(DAMAGE_TYPES))
def test_stats_mask_yields_damage_type(mask: int) -> None:
    row = extract_row("_100", StatsFactory(mask=mask))
    assert row["damage_type"] == DAMAGE_TYPES[mask][0]


@pytest.mark.parametrize("invisible", [True, False])
def test_stats_invisible_controls_camo(invisible: bool) -> None:
    row = extract_row("_100", StatsFactory(invisible=invisible))
    assert row["can_hit_camo"] is not invisible


@pytest.mark.parametrize("pierce", [0, 1, 40])
def test_stats_pierce_flows_to_row(pierce: int) -> None:
    row = extract_row("_100", StatsFactory(pierce=pierce))
    assert row["projectile_pierce"] == pierce


def test_stats_params_not_leaked_as_keys() -> None:
    assert set(StatsFactory(mask=1)) == {"range", "attacks"}
