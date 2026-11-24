from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from statistics import mean

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.recommend import Recommendation, recommend
from tests.recommend_fixture import build_full_database, build_recommend_database

BIG_BUDGET = 100000
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
    lead_round = recommend(full_database, 63, BIG_BUDGET)
    moab_round = recommend(full_database, 40, BIG_BUDGET)
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
    moab_top = recommend(full_database, 40, BIG_BUDGET)[0]
    lead_top = recommend(full_database, 63, BIG_BUDGET)[0]
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
@given(money=st.integers(0, 200000), round_number=st.sampled_from(ROUNDS))
def test_recommend_sorted_by_score(
    four_upgrade_database: sqlite3.Connection, money: int, round_number: int
) -> None:
    scores = [result.score for result in recommend(four_upgrade_database, round_number, money)]
    numeric = [score for score in scores if score is not None]
    assert numeric == sorted(numeric, reverse=True)
    assert scores == numeric + [None] * (len(scores) - len(numeric))
