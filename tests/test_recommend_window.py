from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6 import recommend as recommend_module
from btd6.query import QueryError
from btd6.recommend import Recommendation, recommend
from btd6.rounds import NoRoundDataError
from tests.recommend_fixture import (
    MEDIUM_COSTS,
    build_recommend_database,
    plain_round_fit,
    plain_window_score,
    upgrade_dps,
)

BIG_BUDGET = 100000
NON_CAMO_PATHS = ["0-0-0", "1-0-0", "3-0-0"]
LAST_ROUND = 101


@pytest.fixture
def window_database() -> Iterator[sqlite3.Connection]:
    connection = build_recommend_database()
    yield connection
    connection.close()


def by_path(results: list[Recommendation]) -> dict[str, Recommendation]:
    return {result.path: result for result in results}


def paths_of(results: list[Recommendation]) -> list[str]:
    return [result.path for result in results]


# region horizon


@pytest.mark.parametrize(
    ("horizon", "message"),
    [
        ("5", "horizon must be a whole number, got '5'"),
        (2.5, "horizon must be a whole number, got 2.5"),
        (True, "horizon must be a whole number, got True"),
        (None, "horizon must be a whole number, got None"),
        (0, "horizon must be at least 1, got 0"),
        (-3, "horizon must be at least 1, got -3"),
    ],
)
def test_recommend_horizon_errors(
    window_database: sqlite3.Connection, horizon: object, message: str
) -> None:
    with pytest.raises(QueryError) as caught:
        recommend(window_database, 1, BIG_BUDGET, horizon=horizon)
    assert str(caught.value) == message


@pytest.mark.parametrize("horizon", [1, 2, 5, 1000])
def test_recommend_horizon_accepts_whole_numbers(
    window_database: sqlite3.Connection, horizon: int
) -> None:
    assert recommend(window_database, 1, BIG_BUDGET, horizon=horizon)


def test_recommend_validation_order_money_first(window_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError, match="money must be 0 or more"):
        recommend(window_database, 150, -1, "nightmare", 0, 0)


def test_recommend_validation_order_difficulty_before_limit(
    window_database: sqlite3.Connection,
) -> None:
    with pytest.raises(QueryError, match="nightmare"):
        recommend(window_database, 150, BIG_BUDGET, "nightmare", 0, 0)


def test_recommend_validation_order_limit_before_horizon(
    window_database: sqlite3.Connection,
) -> None:
    with pytest.raises(QueryError, match="limit must be at least 1, got 0"):
        recommend(window_database, 150, BIG_BUDGET, "medium", 0, 0)


def test_recommend_validation_order_horizon_before_round(
    window_database: sqlite3.Connection,
) -> None:
    with pytest.raises(QueryError, match="horizon must be at least 1, got 0"):
        recommend(window_database, 150, BIG_BUDGET, horizon=0)


def test_recommend_validation_order_round_after_horizon_ok(
    window_database: sqlite3.Connection,
) -> None:
    with pytest.raises(QueryError, match="Round 150 is not loaded"):
        recommend(window_database, 150, BIG_BUDGET, horizon=3)


def test_recommend_horizon_checked_without_round_data() -> None:
    connection = build_recommend_database(with_rounds=False)
    with pytest.raises(QueryError, match="horizon must be at least 1"):
        recommend(connection, 1, BIG_BUDGET, horizon=0)
    with pytest.raises(NoRoundDataError):
        recommend(connection, 1, BIG_BUDGET, horizon=2)


def test_recommend_default_horizon_is_five(window_database: sqlite3.Connection) -> None:
    default = recommend(window_database, 1, BIG_BUDGET)
    assert default == recommend(window_database, 1, BIG_BUDGET, horizon=5)
    assert default != recommend(window_database, 1, BIG_BUDGET, horizon=1)


@pytest.mark.parametrize("round_number", [1, 40, 63, 100, 101])
def test_recommend_horizon_one_is_single_round_scoring(
    window_database: sqlite3.Connection, round_number: int
) -> None:
    for result in recommend(window_database, round_number, BIG_BUDGET, horizon=1):
        assert result.first_leak_round is None
        assert not any(reason.startswith("fails_") for reason in result.reasons)


@pytest.mark.parametrize("horizon", [1, 2, 3, 5])
def test_recommend_window_score_is_decay_weighted_mean(
    window_database: sqlite3.Connection, horizon: int
) -> None:
    results = by_path(recommend(window_database, 1, BIG_BUDGET, horizon=horizon))
    for path in MEDIUM_COSTS:
        expected = plain_window_score(path, 1, horizon)
        assert results[path].score == pytest.approx(expected, rel=1e-6)


def test_recommend_window_two_rounds_uses_decay_weight(
    window_database: sqlite3.Connection,
) -> None:
    result = by_path(recommend(window_database, 2, BIG_BUDGET, horizon=2))["1-0-0"]
    expected = (plain_round_fit("1-0-0", 2) + 0.75 * plain_round_fit("1-0-0", 3)) / 1.75
    assert result.score == pytest.approx(expected, rel=1e-6)


def test_recommend_window_truncated_at_last_round(window_database: sqlite3.Connection) -> None:
    assert recommend(window_database, LAST_ROUND, BIG_BUDGET, horizon=5) == recommend(
        window_database, LAST_ROUND, BIG_BUDGET, horizon=1
    )


def test_recommend_window_truncated_equals_exact_window(
    window_database: sqlite3.Connection,
) -> None:
    near_end = recommend(window_database, 100, BIG_BUDGET, horizon=5)
    assert near_end == recommend(window_database, 100, BIG_BUDGET, horizon=2)
    assert near_end == recommend(window_database, 100, BIG_BUDGET, horizon=1000)


def test_recommend_leak_in_last_round_of_window(window_database: sqlite3.Connection) -> None:
    results = by_path(recommend(window_database, 100, BIG_BUDGET, horizon=5))
    for path in NON_CAMO_PATHS:
        assert results[path].first_leak_round == LAST_ROUND
        assert results[path].reasons[-1] == "fails_camo_at_101"
    assert results["0-0-4"].first_leak_round is None
    assert not any(reason.startswith("fails_") for reason in results["0-0-4"].reasons)


def test_recommend_leak_not_seen_when_window_ends_before_camo(
    window_database: sqlite3.Connection,
) -> None:
    results = recommend(window_database, 100, BIG_BUDGET, horizon=1)
    assert all(result.first_leak_round is None for result in results)


def test_recommend_leak_zeroes_that_round(window_database: sqlite3.Connection) -> None:
    result = by_path(recommend(window_database, 100, BIG_BUDGET, horizon=2))["0-0-0"]
    round_fit = upgrade_dps("0-0-0") / MEDIUM_COSTS["0-0-0"]
    assert result.score == pytest.approx(round_fit / 1.75, rel=1e-6)


def test_recommend_leak_first_camo_round_in_fixture_is_99(
    window_database: sqlite3.Connection,
) -> None:
    results = by_path(recommend(window_database, 97, BIG_BUDGET, horizon=5))
    for path in NON_CAMO_PATHS:
        assert results[path].first_leak_round == 99
        assert results[path].reasons[-1] == "fails_camo_at_99"
        assert "fails_camo_at_101" not in results[path].reasons
    assert results["0-0-4"].first_leak_round is None


def test_recommend_non_leakers_rank_first(window_database: sqlite3.Connection) -> None:
    results = recommend(window_database, 97, BIG_BUDGET, horizon=5)
    assert paths_of(results)[0] == "0-0-4"
    leaker_scores = [result.score for result in results if result.first_leak_round]
    assert max(leaker_scores) > results[0].score


def test_recommend_leakers_ordered_by_score(window_database: sqlite3.Connection) -> None:
    results = recommend(window_database, 97, BIG_BUDGET, horizon=5)[1:]
    scores = [result.score for result in results]
    assert scores == sorted(scores, reverse=True)


def test_recommend_leak_property_needed_later(window_database: sqlite3.Connection) -> None:
    results = by_path(recommend(window_database, 26, BIG_BUDGET, horizon=3))
    assert results["0-0-0"].first_leak_round == 28
    assert results["1-0-0"].reasons[-1] == "fails_lead_at_28"
    assert results["3-0-0"].first_leak_round is None
    assert results["0-0-4"].first_leak_round is None


def test_recommend_fails_codes_sorted_by_round_then_need(
    window_database: sqlite3.Connection,
) -> None:
    results = by_path(recommend(window_database, 34, BIG_BUDGET, horizon=4))
    assert results["0-0-0"].reasons[-2:] == ("fails_camo_at_36", "fails_lead_at_37")
    assert results["0-0-0"].first_leak_round == 36
    assert results["3-0-0"].reasons[-1:] == ("fails_camo_at_36",)
    assert not any(reason.startswith("fails_") for reason in results["0-0-4"].reasons)


def test_recommend_fails_codes_same_round_camo_before_lead(
    window_database: sqlite3.Connection,
) -> None:
    window_database.execute("UPDATE round_groups SET is_camo = 1 WHERE round = 28")
    window_database.commit()
    results = by_path(recommend(window_database, 26, BIG_BUDGET, horizon=3))
    assert results["0-0-0"].reasons[-2:] == ("fails_camo_at_28", "fails_lead_at_28")
    assert results["3-0-0"].reasons[-1:] == ("fails_camo_at_28",)


def test_recommend_each_need_reported_once_at_first_round(
    window_database: sqlite3.Connection,
) -> None:
    results = by_path(recommend(window_database, 34, BIG_BUDGET, horizon=5))
    camo_codes = [code for code in results["0-0-0"].reasons if code.startswith("fails_camo")]
    assert camo_codes == ["fails_camo_at_36"]


def test_recommend_current_round_needs_stay_hard_filters(
    window_database: sqlite3.Connection,
) -> None:
    results = recommend(window_database, 37, BIG_BUDGET, horizon=5)
    assert paths_of(results) == ["0-0-4"]


PROPERTY_SETTINGS = settings(max_examples=40, deadline=None)


@PROPERTY_SETTINGS
@given(
    round_number=st.integers(1, LAST_ROUND),
    horizon=st.integers(1, 8),
    money=st.integers(0, 200000),
)
def test_recommend_leak_groups_then_scores(
    window_database_module: sqlite3.Connection, round_number: int, horizon: int, money: int
) -> None:
    results = recommend(window_database_module, round_number, money, horizon=horizon)
    leaks = [result.first_leak_round is not None for result in results]
    assert leaks == sorted(leaks)
    for group in (False, True):
        scores = [item.score for item in results if (item.first_leak_round is not None) == group]
        numeric = [score for score in scores if score is not None]
        assert numeric == sorted(numeric, reverse=True)
        assert scores == numeric + [None] * (len(scores) - len(numeric))
    for result in results:
        has_fail = any(reason.startswith("fails_") for reason in result.reasons)
        assert has_fail == (result.first_leak_round is not None)
        assert (
            round_number < (result.first_leak_round or round_number + 1) <= round_number + horizon
        )


@PROPERTY_SETTINGS
@given(round_number=st.integers(1, LAST_ROUND), money=st.integers(0, 200000))
def test_recommend_horizon_one_never_leaks(
    window_database_module: sqlite3.Connection, round_number: int, money: int
) -> None:
    results = recommend(window_database_module, round_number, money, horizon=1)
    assert all(result.first_leak_round is None for result in results)


@pytest.fixture(scope="module")
def window_database_module() -> Iterator[sqlite3.Connection]:
    connection = build_recommend_database()
    yield connection
    connection.close()


# endregion


def test_recommend_module_exposes_window_constants() -> None:
    assert recommend_module.DEFAULT_HORIZON == 5
    assert recommend_module.HORIZON_DECAY == 0.75
