from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from statistics import mean

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.query import UpgradeFilters
from btd6.ranking import rank_upgrades
from btd6.recommend import Recommendation, recommend
from tests.recommend_fixture import (
    build_full_database,
    build_recommend_database,
    round_density,
)

BIG_BUDGET = 100000
EARLY_BUDGET = 5000
TOP_COUNT = 5
ROUNDS = [1, 40, 63]
PROPERTY_SETTINGS = settings(max_examples=50, deadline=None)


@pytest.fixture
def full_database(offline_costs_wiki: None) -> Iterator[sqlite3.Connection]:
    connection = build_full_database()
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def four_upgrade_database() -> Iterator[sqlite3.Connection]:
    connection = build_recommend_database()
    yield connection
    connection.close()


def identities(results: list[Recommendation]) -> set[tuple[str, str]]:
    return {(result.tower_name, result.path) for result in results}


def top_pierce(results: list[Recommendation]) -> float:
    return mean(result.projectile_pierce for result in results[:TOP_COUNT])


def test_recommend_round_63_pops_lead(full_database: sqlite3.Connection) -> None:
    results = recommend(full_database, 63, BIG_BUDGET)
    assert results
    assert all("pops_lead" in result.reasons for result in results)
    assert all("hits_camo" not in result.reasons for result in results)


def test_recommend_round_63_prefers_pierce(full_database: sqlite3.Connection) -> None:
    lead_round = recommend(full_database, 63, BIG_BUDGET, horizon=1)
    moab_round = recommend(full_database, 40, BIG_BUDGET, horizon=1)
    assert len(lead_round) >= TOP_COUNT
    assert len(moab_round) >= TOP_COUNT
    assert top_pierce(lead_round) > top_pierce(moab_round)


def test_recommend_round_40_prefers_single_target(full_database: sqlite3.Connection) -> None:
    """Single-target value per dollar of the top pick is higher in the MOAB round.

    The spec oracle compares raw `moab_dps` of the two top results. On this fixture that
    is 22.2 (round 40, Super Monkey 0-0-0) against 100 (round 63, Super Monkey 3-2-0),
    so the raw comparison cannot hold: the score divides by cost and round 40 favours
    cheap upgrades. The invariant that does hold is `moab_dps / total_cost`.
    """
    moab_top = recommend(full_database, 40, BIG_BUDGET, horizon=1)[0]
    lead_top = recommend(full_database, 63, BIG_BUDGET, horizon=1)[0]
    assert moab_top.moab_dps / moab_top.total_cost >= lead_top.moab_dps / lead_top.total_cost


@PROPERTY_SETTINGS
@given(
    budgets=st.tuples(st.integers(0, 200000), st.integers(0, 200000)).map(sorted),
    round_number=st.sampled_from(ROUNDS),
)
def test_recommend_budget_monotonic(
    four_upgrade_database: sqlite3.Connection, budgets: list[int], round_number: int
) -> None:
    smaller = recommend(four_upgrade_database, round_number, budgets[0])
    larger = recommend(four_upgrade_database, round_number, budgets[1])
    assert identities(smaller) <= identities(larger)


@PROPERTY_SETTINGS
@given(money=st.integers(0, 200000), round_number=st.sampled_from(ROUNDS))
def test_recommend_never_exceeds_money(
    four_upgrade_database: sqlite3.Connection, money: int, round_number: int
) -> None:
    results = recommend(four_upgrade_database, round_number, money)
    assert all(result.total_cost <= money for result in results)


@PROPERTY_SETTINGS
@given(
    money=st.integers(0, 200000),
    round_number=st.sampled_from(ROUNDS),
    horizon=st.integers(1, 6),
)
def test_recommend_sorted_by_leak_group_then_score(
    four_upgrade_database: sqlite3.Connection, money: int, round_number: int, horizon: int
) -> None:
    results = recommend(four_upgrade_database, round_number, money, horizon=horizon)
    leaks = [result.first_leak_round is not None for result in results]
    assert leaks == sorted(leaks)
    for leaking in (False, True):
        group = [item.score for item in results if (item.first_leak_round is not None) == leaking]
        numeric = [score for score in group if score is not None]
        assert numeric == sorted(numeric, reverse=True)
        assert group == numeric + [None] * (len(group) - len(numeric))


def hits_camo(connection: sqlite3.Connection, result: Recommendation) -> bool:
    frame = rank_upgrades(connection, UpgradeFilters(can_hit_camo=True))
    camo_paths = set(zip(frame["tower_name"], frame["path"], strict=True))
    return (result.tower_name, result.path) in camo_paths


def test_recommend_round_1_does_not_pick_ice_monkey_base(full_database: sqlite3.Connection) -> None:
    """Ice Monkey 0-0-0 has pierce 40 but range 20, so round 1's crowd caps it near 1.8."""
    results = recommend(full_database, 1, EARLY_BUDGET)
    ice_base = next(
        item for item in results if (item.tower_name, item.path) == ("Ice Monkey", "0-0-0")
    )
    assert (results[0].tower_name, results[0].path) != ("Ice Monkey", "0-0-0")
    assert ice_base.projectile_pierce == 40
    assert ice_base.effective_pierce == pytest.approx(round_density(1) * 2 * 20, rel=1e-6)
    assert ice_base.effective_pierce < 2


def test_recommend_round_20_prefers_camo_capable_upgrade(full_database: sqlite3.Connection) -> None:
    """Round 24 has a camo group, so an upgrade that cannot hit it leaks inside the window."""
    results = recommend(full_database, 20, EARLY_BUDGET, horizon=5)
    top_result = results[0]
    assert top_result.first_leak_round is None
    assert hits_camo(full_database, top_result)
    assert not any(reason.startswith("fails_") for reason in top_result.reasons)
    leakers = [result for result in results if result.first_leak_round is not None]
    assert leakers
    assert {result.first_leak_round for result in leakers} == {24}
    assert not any(hits_camo(full_database, result) for result in leakers)


def test_recommend_round_20_single_round_ignores_later_camo(
    full_database: sqlite3.Connection,
) -> None:
    results = recommend(full_database, 20, EARLY_BUDGET, horizon=1)
    assert all(result.first_leak_round is None for result in results)
    assert not hits_camo(full_database, results[0])
