from __future__ import annotations

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
    EffectFactory,
    make_attack,
    make_stats,
    stored_upgrade_id,
    with_effects,
)


def stats_with(
    rate: float | None, projectile: dict[str, Any], *named: tuple[str, dict[str, Any]]
) -> dict[str, Any]:
    return make_stats(make_attack("Attack", rate, {"Projectile": with_effects(projectile, *named)}))


def figures_of(database: sqlite3.Connection, stats: dict[str, Any]) -> tuple[Any, Any]:
    load_tower(database, "Glue Gunner", {"_200": stats}, "Support")
    upgrade_id = stored_upgrade_id(database, "Glue Gunner", "2-0-0")
    return upgrade_dps(database, upgrade_id), upgrade_moab_dps(database, upgrade_id)


def assert_figures(actual: tuple[Any, Any], expected: tuple[Any, Any]) -> None:
    for value, wanted in zip(actual, expected, strict=True):
        if wanted is None:
            assert value is None
        else:
            assert value == pytest.approx(wanted, rel=1e-6)


def effect_only(rate, count, damage, interval, lifespan, immediate, **extra) -> dict[str, Any]:
    projectile = {} if count is None else {"count": count}
    effect = EffectFactory(
        damage=damage, interval=interval, lifespan=lifespan, triggerImmediate=immediate, **extra
    )
    return stats_with(rate, projectile, ("Damage over time", effect))


ORACLES = [
    pytest.param((1, None, 1, 2, 11, False), 0.5, id="glue_200_capped"),
    pytest.param((4, 1, 450, 2.95, 3, False), 112.5, id="ninja_below_cap"),
    pytest.param((1, 1, 30, 1, 0.95, True), 30, id="immediate_tick_counts"),
    pytest.param((1, None, 5, 2, 1, False), 0.0, id="zero_ticks_still_usable"),
    pytest.param((40, 2, 10, 1, 3, False), 1.5, id="count_multiplies"),
    pytest.param((1, None, 1, 0.1, 0.3, False), 3, id="floating_point_tick_epsilon"),
    pytest.param((1, 0, 10, 1, 3, False), 0.0, id="count_zero_gives_nothing"),
    pytest.param((1, None, 4, 1, 2, True), 4.0, id="immediate_plus_lifespan_ticks_capped"),
]


@pytest.mark.parametrize(("shape", "expected"), ORACLES)
def test_effect_only_dps(database, shape, expected) -> None:
    assert_figures(figures_of(database, effect_only(*shape)), (expected, expected))


def test_effect_adds_to_projectile_damage(database) -> None:
    stats = stats_with(0.5, {"damage": 2, "count": 1}, ("Damage over time", EffectFactory()))
    assert_figures(figures_of(database, stats), (4.5, 4.5))


def test_effect_moab_bonus_splits_figures(database) -> None:
    stats = effect_only(1, None, 2, 1, 3.05, False, damageModifierForMoabs=3)
    assert_figures(figures_of(database, stats), (2, 5))


def test_moab_only_effect_counts_only_toward_moab_dps(database) -> None:
    stats = stats_with(
        1, {"damage": 1}, ("Damage over time", EffectFactory(filterOutNonMoabs=True))
    )
    assert_figures(figures_of(database, stats), (1.0, 1.5))


def test_moab_only_effect_alone_has_no_plain_dps(database) -> None:
    stats = effect_only(1, None, 1, 2, 11, False, filterOutNonMoabs=True)
    assert_figures(figures_of(database, stats), (None, 0.5))


def test_effects_sum_within_an_attack(database) -> None:
    stats = stats_with(
        1, {}, ("One", EffectFactory()), ("Two", EffectFactory(damage=2, interval=4, lifespan=8))
    )
    assert_figures(figures_of(database, stats), (1.0, 1.0))


def test_effect_counts_when_projectile_damage_is_null(database) -> None:
    stats = stats_with(1, {"pierce": 3}, ("Damage over time", EffectFactory()))
    assert_figures(figures_of(database, stats), (0.5, 0.5))


def test_effect_counts_when_projectile_damage_is_unlimited(database) -> None:
    stats = stats_with(1, {"damage": UNLIMITED}, ("Damage over time", EffectFactory()))
    assert_figures(figures_of(database, stats), (0.5, 0.5))


def test_projectile_without_damage_or_effects_stays_null(database) -> None:
    assert_figures(figures_of(database, stats_with(1, {"pierce": 3})), (None, None))


def test_non_damaging_effect_leaves_dps_null(database) -> None:
    stats = stats_with(1, {"pierce": 3}, ("Freeze", {"lifespan": 2, "interval": 1}))
    assert_figures(figures_of(database, stats), (None, None))


@pytest.mark.parametrize("rate", [None, 0], ids=["null_rate", "zero_rate"])
def test_effect_on_unusable_attack_is_skipped(database, rate) -> None:
    stats = stats_with(rate, {"damage": 1}, ("Damage over time", EffectFactory()))
    assert_figures(figures_of(database, stats), (None, None))


def test_effect_on_second_attack_adds(database) -> None:
    first = make_attack("Attack", 1, {"Projectile": {"damage": 1}})
    second = make_attack(
        "Other", 2, {"Projectile": with_effects({}, ("Damage over time", EffectFactory()))}
    )
    assert_figures(figures_of(database, make_stats(first, second)), (1.5, 1.5))


def test_all_upgrade_dps_includes_effects(database) -> None:
    figures_of(database, effect_only(1, None, 1, 2, 11, False))
    upgrade_id = stored_upgrade_id(database, "Glue Gunner", "2-0-0")
    assert_figures(all_upgrade_dps(database)[upgrade_id], (0.5, 0.5))


@settings(max_examples=40, deadline=None)
@given(
    rate=st.floats(0.05, 5),
    damage=st.integers(1, 100),
    interval=st.floats(0.1, 5),
    lifespan=st.floats(0, 30),
    bonus=st.integers(0, 50),
)
def test_effect_dps_never_exceeds_tick_cap(rate, damage, interval, lifespan, bonus) -> None:
    connection = connect(":memory:")
    initialize_database(connection)
    stats = effect_only(rate, None, damage, interval, lifespan, False, damageModifierForMoabs=bonus)
    plain, moab = figures_of(connection, stats)
    connection.close()
    assert 0 <= plain <= damage / interval + 1e-9
    assert plain <= moab <= (damage + bonus) / interval + 1e-9
