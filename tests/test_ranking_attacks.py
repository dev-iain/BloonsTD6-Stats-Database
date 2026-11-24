from __future__ import annotations

import math
import sqlite3

import pandas
import pytest

from btd6.db.loader import load_tower
from btd6.query import UpgradeFilters, search_upgrades
from btd6.ranking import rank_upgrades
from tests.factories import (
    UNLIMITED,
    alchemist_040,
    alchemist_220,
    druid_030,
    druid_040,
    druid_400,
    make_attack,
    make_stats,
    ninja_003,
    wizard_005,
    wizard_400,
)

METRIC_COLUMNS = ["dps", "moab_dps", "pierce_weighted_dps", "damage_per_dollar"]


@pytest.fixture
def magic_database(database) -> sqlite3.Connection:
    load_tower(database, "Ninja Monkey", {"_003": ninja_003()}, "Primary")
    load_tower(database, "Wizard Monkey", {"_400": wizard_400()}, "Magic")
    load_tower(database, "Druid", {"_030": druid_030(), "_400": druid_400()}, "Magic")
    load_tower(database, "Alchemist", {"_220": alchemist_220()}, "Magic")
    return database


def metric_of(frame: pandas.DataFrame, tower: str, path: str, column: str) -> float:
    row = frame[(frame["tower_name"] == tower) & (frame["path"] == path)]
    return row[column].iloc[0]


@pytest.mark.parametrize(
    ("tower", "path", "dps", "moab_dps"),
    [
        ("Ninja Monkey", "0-0-3", 6.70802, 6.70802),
        ("Wizard Monkey", "4-0-0", 21.81818, 58.18182),
        ("Druid", "0-3-0", 7.65734, 7.65734),
        ("Druid", "4-0-0", 6.34980, 6.34980),
    ],
)
def test_rank_upgrades_uses_per_attack_sum(magic_database, tower, path, dps, moab_dps) -> None:
    result = rank_upgrades(magic_database, metric="dps")
    assert metric_of(result, tower, path, "dps") == pytest.approx(dps, rel=1e-5)
    assert metric_of(result, tower, path, "moab_dps") == pytest.approx(moab_dps, rel=1e-5)


def test_rank_upgrades_ninja_003_is_not_null(magic_database) -> None:
    result = rank_upgrades(magic_database, metric="dps")
    assert not pandas.isna(metric_of(result, "Ninja Monkey", "0-0-3", "dps"))


def test_rank_upgrades_alchemist_220_null_dps_ranks_last(magic_database) -> None:
    for metric in ("dps", "moab_dps"):
        result = rank_upgrades(magic_database, metric=metric)
        last = result.iloc[-1]
        assert (last["tower_name"], last["path"]) == ("Alchemist", "2-2-0")
        assert pandas.isna(last["dps"]) and pandas.isna(last["moab_dps"])


def test_rank_upgrades_by_moab_dps_order(magic_database) -> None:
    result = rank_upgrades(magic_database, metric="moab_dps")
    assert list(zip(result["tower_name"], result["path"], strict=True)) == [
        ("Wizard Monkey", "4-0-0"),
        ("Druid", "0-3-0"),
        ("Ninja Monkey", "0-0-3"),
        ("Druid", "4-0-0"),
        ("Alchemist", "2-2-0"),
    ]


def test_rank_upgrades_wizard_moab_dps_beats_plain_dps(magic_database) -> None:
    result = rank_upgrades(magic_database, UpgradeFilters(tower_name="Wizard Monkey"))
    assert result["moab_dps"].iloc[0] > result["dps"].iloc[0]


@pytest.mark.parametrize(
    "metric", ["dps", "moab_dps", "damage_per_dollar", "pierce_damage_per_dollar"]
)
def test_rank_upgrades_never_infinite_with_unlimited_sentinel(magic_database, metric) -> None:
    result = rank_upgrades(magic_database, UpgradeFilters(tower_name="Druid"), metric=metric)
    assert len(result) == 2
    for column in [*METRIC_COLUMNS, "pierce_damage_per_dollar"]:
        assert not any(math.isinf(value) for value in result[column].dropna()), column
    assert result["dps"].max() < 1000


def test_rank_upgrades_unlimited_pierce_first_projectile_gives_null_pierce_metric(
    database,
) -> None:
    vine_first = make_stats(
        make_attack(
            "Vine",
            2.6,
            {
                "Collidable": {"damage": UNLIMITED, "pierce": UNLIMITED},
                "Projectile": {"damage": 1, "pierce": 20},
            },
        )
    )
    load_tower(database, "Druid", {"_030": vine_first}, "Magic")
    result = rank_upgrades(database, metric="pierce_damage_per_dollar")
    assert pandas.isna(result["pierce_weighted_dps"].iloc[0])
    assert result["dps"].iloc[0] == pytest.approx(1 / 2.6, rel=1e-6)


def test_rank_upgrades_wizard_005_stable_lower_bound(database) -> None:
    load_tower(database, "Wizard Monkey", {"_005": wizard_005()}, "Magic")
    result = rank_upgrades(database, metric="dps")
    assert result["dps"].iloc[0] >= 1 / 0.275 + 2 / 1.5 - 1e-6


def test_rank_upgrades_wizard_005_moab_and_bfb_are_alternatives(database) -> None:
    """DPS takes the smallest bloon-class alternative (40), MOAB DPS the largest (100)."""
    load_tower(database, "Wizard Monkey", {"_005": wizard_005()}, "Magic")
    result = rank_upgrades(database, metric="dps")
    assert result["dps"].iloc[0] == pytest.approx(18.30303, rel=1e-5)
    assert result["moab_dps"].iloc[0] == pytest.approx(38.30303, rel=1e-5)


def test_rank_upgrades_ranks_by_real_damage_across_towers(magic_database) -> None:
    result = rank_upgrades(magic_database, metric="dps")
    assert list(result["path"])[:2] == ["4-0-0", "0-3-0"]
    assert result["tower_name"].iloc[0] == "Wizard Monkey"


def test_search_upgrades_rows_unchanged_by_attack_tables(magic_database) -> None:
    rows = search_upgrades(magic_database, UpgradeFilters(tower_name="Ninja Monkey"))
    assert [row["path"] for row in rows] == ["0-0-3"]
    assert rows[0]["projectile_damage"] is None


@pytest.mark.parametrize("descending", [False, True])
def test_ability_cooldown_zero_sorts_like_no_ability(database, descending) -> None:
    load_tower(database, "Druid", {"_040": druid_040()}, "Magic")
    load_tower(database, "Alchemist", {"_040": alchemist_040(), "_220": alchemist_220()}, "Magic")
    rows = search_upgrades(database, sort_by="ability_cooldown", descending=descending)
    order = [(row["tower_name"], row["path"]) for row in rows]
    assert order == [("Alchemist", "0-4-0"), ("Alchemist", "2-2-0"), ("Druid", "0-4-0")]
