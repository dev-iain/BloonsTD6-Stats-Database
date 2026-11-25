from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import FrozenInstanceError

import pytest

from btd6 import recommend as recommend_module
from btd6.db.cost_loader import load_costs
from btd6.query import QueryError, UpgradeFilters
from btd6.recommend import (
    HIGH_PIERCE,
    MIN_PROPERTY_SHARE,
    Recommendation,
    filters_for_threats,
    reasons_for,
    recommend,
    round_score,
    sort_key,
)
from btd6.rounds import NoRoundDataError
from tests.factories import CostsFactory, UpgradeRowFactory
from tests.recommend_fixture import (
    FIXTURE_RANGE,
    build_recommend_database,
    camo_specs,
    capped_pierce,
    load_round_data,
    make_recommendation,
    make_threats,
    plain_window_score,
    round_density,
)
from tests.test_ranking import (
    NULL_RATE_STATS,
    UPGRADE_STATS,
    build_database,
    insert_upgrade_rows,
)

BASE_PATHS = ["3-0-0", "1-0-0", "0-0-0", "0-0-4"]
ROUND_ONE_DENSITY = (20 / 17.5125) / 25
ROUND_ONE_CROWD = ROUND_ONE_DENSITY * 2 * FIXTURE_RANGE
SINGLE_ROUND_SCORES = [
    100 * min(6, ROUND_ONE_CROWD) / 27000,
    (1 / 0.045 * 2) / 4500,
    (1 / 0.045) / 2500,
    (2 / 0.0225 * min(8, ROUND_ONE_CROWD)) / 67855,
]
BIG_BUDGET = 100000
NUMERIC_FIELDS = (
    "dps",
    "moab_dps",
    "pierce_weighted_dps",
    "projectile_pierce",
    "effective_pierce",
)


@pytest.fixture
def recommend_database() -> Iterator[sqlite3.Connection]:
    connection = build_recommend_database()
    yield connection
    connection.close()


def paths_of(results: list[Recommendation]) -> list[str]:
    return [result.path for result in results]


def cost_of(results: list[Recommendation], path: str) -> int:
    return next(result.total_cost for result in results if result.path == path)


def test_constants() -> None:
    assert MIN_PROPERTY_SHARE == 0.05
    assert HIGH_PIERCE == 5
    assert recommend_module.DEFAULT_HORIZON == 5
    assert recommend_module.HORIZON_DECAY == 0.75


# region recommend


def test_recommend_all_base(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 1, BIG_BUDGET)
    assert paths_of(results) == BASE_PATHS
    expected = [plain_window_score(path, 1, 5) for path in BASE_PATHS]
    assert [result.score for result in results] == pytest.approx(expected, rel=1e-6)
    assert all(result.first_leak_round is None for result in results)


def test_recommend_single_round_scores_use_capped_pierce(
    recommend_database: sqlite3.Connection,
) -> None:
    results = recommend(recommend_database, 1, BIG_BUDGET, horizon=1)
    assert paths_of(results) == BASE_PATHS
    assert [result.score for result in results] == pytest.approx(SINGLE_ROUND_SCORES, rel=1e-6)
    assert ROUND_ONE_CROWD == pytest.approx(round_density(1) * 100)
    assert capped_pierce("3-0-0", round_density(1)) == pytest.approx(ROUND_ONE_CROWD)


def test_recommend_money_equal_to_cost(recommend_database: sqlite3.Connection) -> None:
    assert paths_of(recommend(recommend_database, 1, 4500, horizon=1)) == ["1-0-0", "0-0-0"]


def test_recommend_money_below_cheapest(recommend_database: sqlite3.Connection) -> None:
    assert recommend(recommend_database, 1, 2499) == []


def test_recommend_negative_money(recommend_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        recommend(recommend_database, 1, -1)


def test_recommend_money_not_int(recommend_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        recommend(recommend_database, 1, "5000")


def test_recommend_easy(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 1, BIG_BUDGET, difficulty="easy")
    assert cost_of(results, "0-0-0") == 2125


def test_recommend_hard(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 1, BIG_BUDGET, difficulty="hard")
    assert cost_of(results, "0-0-0") == 2700


def test_recommend_impoppable(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 1, BIG_BUDGET, difficulty="impoppable")
    assert cost_of(results, "0-0-0") == 3000


def test_recommend_invalid_difficulty(recommend_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        recommend(recommend_database, 1, BIG_BUDGET, difficulty="nightmare")


def test_recommend_moab_round(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 40, BIG_BUDGET, horizon=1)
    assert paths_of(results) == ["0-0-0", "1-0-0", "3-0-0", "0-0-4"]
    assert all(result.reasons[-1] == "high_single_target" for result in results)


def test_recommend_lead_round(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 63, BIG_BUDGET, horizon=1)
    assert paths_of(results) == ["3-0-0", "0-0-4"]
    assert results[0].reasons == ("affordable", "pops_lead", "high_pierce")


def test_recommend_camo_round(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 101, BIG_BUDGET)
    assert paths_of(results) == ["0-0-4"]
    assert results[0].reasons[:2] == ("affordable", "hits_camo")


def test_recommend_round_not_loaded(recommend_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        recommend(recommend_database, 150, BIG_BUDGET)


def test_recommend_limit_zero(recommend_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        recommend(recommend_database, 1, BIG_BUDGET, limit=0)


def test_recommend_limit_one(recommend_database: sqlite3.Connection) -> None:
    assert paths_of(recommend(recommend_database, 1, BIG_BUDGET, limit=1)) == ["3-0-0"]


def test_recommend_limit_above_count(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 1, BIG_BUDGET, limit=10)
    assert paths_of(results) == BASE_PATHS
    assert results == recommend(recommend_database, 1, BIG_BUDGET)


def test_recommend_negative_limit(recommend_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        recommend(recommend_database, 1, BIG_BUDGET, limit=-1)


def test_recommend_no_rounds_loaded() -> None:
    connection = build_recommend_database(with_rounds=False)
    with pytest.raises(NoRoundDataError):
        recommend(connection, 1, BIG_BUDGET)


def test_recommend_costs_not_loaded() -> None:
    connection = build_recommend_database(with_costs=False)
    assert recommend(connection, 1, BIG_BUDGET) == []


def test_recommend_money_bool(recommend_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        recommend(recommend_database, 1, True)


def test_recommend_round_not_int(recommend_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        recommend(recommend_database, "1", BIG_BUDGET)


def test_recommend_zero_money(recommend_database: sqlite3.Connection) -> None:
    assert recommend(recommend_database, 1, 0) == []


def test_recommend_pierce_flips_with_moab_share(recommend_database: sqlite3.Connection) -> None:
    plain = paths_of(recommend(recommend_database, 1, BIG_BUDGET, horizon=1))
    moab = paths_of(recommend(recommend_database, 40, BIG_BUDGET, horizon=1))
    assert plain.index("1-0-0") < plain.index("0-0-0")
    assert moab.index("1-0-0") > moab.index("0-0-0")


def test_recommend_returns_recommendations(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 63, BIG_BUDGET, horizon=1)
    assert results
    for result in results:
        assert isinstance(result, Recommendation)
        assert isinstance(result.reasons, tuple)
        assert result.reasons[0] == "affordable"
        assert result.tower_name == "Super Monkey"
    with pytest.raises(FrozenInstanceError):
        results[0].score = 0.0  # type: ignore[misc]


def test_recommend_fields_match_worked_example(recommend_database: sqlite3.Connection) -> None:
    top_result = recommend(recommend_database, 63, BIG_BUDGET, horizon=1)[0]
    assert (top_result.path, top_result.total_cost) == ("3-0-0", 27000)
    assert top_result.dps == pytest.approx(100, rel=1e-6)
    assert top_result.moab_dps == pytest.approx(100, rel=1e-6)
    assert top_result.pierce_weighted_dps == pytest.approx(600, rel=1e-6)
    assert top_result.projectile_pierce == pytest.approx(6, rel=1e-6)
    assert top_result.effective_pierce == pytest.approx(6, rel=1e-6)
    assert top_result.first_leak_round is None


@pytest.mark.parametrize(
    ("path", "expected"),
    [("0-0-0", 1.0), ("1-0-0", 2.0), ("3-0-0", ROUND_ONE_CROWD), ("0-0-4", ROUND_ONE_CROWD)],
)
def test_recommend_effective_pierce_field_is_capped_by_crowd(
    recommend_database: sqlite3.Connection, path: str, expected: float
) -> None:
    results = recommend(recommend_database, 1, BIG_BUDGET)
    found = next(result for result in results if result.path == path)
    assert found.effective_pierce == pytest.approx(expected, rel=1e-6)
    assert found.projectile_pierce == UPGRADE_STATS[path]["projectile_pierce"]


def test_recommend_high_pierce_needs_effective_pierce(
    recommend_database: sqlite3.Connection,
) -> None:
    results = recommend(recommend_database, 1, BIG_BUDGET, horizon=1)
    assert all("high_pierce" not in result.reasons for result in results)
    assert all(result.reasons == ("affordable",) for result in results)


def test_recommend_tie_breaks_by_name_then_path() -> None:
    stats = {**camo_specs()["0-0-0"], "can_hit_camo": True}
    specs = {"1-0-0": stats, "0-1-0": stats}
    connection = build_database(specs, with_costs=False)
    connection.execute("UPDATE towers SET name = 'Zeta Monkey'")
    connection.commit()
    insert_upgrade_rows(connection, [UpgradeRowFactory.build(path=path, **stats) for path in specs])
    for name in ("Super Monkey", "Zeta Monkey"):
        load_costs(connection, name, CostsFactory.build())
    load_round_data(connection)
    results = recommend(connection, 1, BIG_BUDGET)
    assert [(item.tower_name, item.path) for item in results] == [
        ("Super Monkey", "0-1-0"),
        ("Super Monkey", "1-0-0"),
        ("Zeta Monkey", "0-1-0"),
        ("Zeta Monkey", "1-0-0"),
    ]
    assert len({item.score for item in results}) == 1
    assert len({item.total_cost for item in results}) == 1


@pytest.mark.parametrize(
    ("money", "limit", "message"),
    [
        (1.5, None, "money must be a whole number"),
        (True, None, "money must be a whole number"),
        (-1, None, "money must be 0 or more, got -1"),
        (BIG_BUDGET, 2.5, "limit must be a whole number"),
        (BIG_BUDGET, True, "limit must be a whole number"),
    ],
)
def test_recommend_error_messages(
    recommend_database: sqlite3.Connection, money: object, limit: object, message: str
) -> None:
    with pytest.raises(QueryError, match=message):
        recommend(recommend_database, 1, money, limit=limit)


@pytest.mark.parametrize("null_stat", ["attack_rate", "projectile_pierce"])
def test_recommend_null_stats_are_none_and_last(null_stat: str) -> None:
    null_stats = {**NULL_RATE_STATS, "attack_rate": 0.045, null_stat: None}
    connection = build_database({**UPGRADE_STATS, "0-1-0": null_stats})
    load_round_data(connection)
    results = recommend(connection, 1, BIG_BUDGET)
    connection.close()
    assert results[-1].path == "0-1-0"
    assert results[-1].score is None
    assert all(result.score is not None for result in results[:-1])
    assert getattr(results[-1], null_stat.replace("attack_rate", "dps")) is None
    assert results[-1].first_leak_round is None
    for field in (
        "dps",
        "moab_dps",
        "pierce_weighted_dps",
        "projectile_pierce",
        "effective_pierce",
    ):
        value = getattr(results[-1], field)
        assert value is None or value == value


# endregion


def test_filters_for_threats_all_base() -> None:
    assert filters_for_threats(make_threats()) == UpgradeFilters()


def test_filters_for_threats_camo() -> None:
    assert filters_for_threats(make_threats(camo_share=0.01)) == UpgradeFilters(can_hit_camo=True)


def test_filters_for_threats_lead_below_threshold() -> None:
    assert filters_for_threats(make_threats(lead=0.0499)) == UpgradeFilters()


def test_filters_for_threats_lead_at_threshold() -> None:
    assert filters_for_threats(make_threats(lead=0.05)) == UpgradeFilters(can_pop_lead=True)


def test_filters_for_threats_lead_above_threshold() -> None:
    assert filters_for_threats(make_threats(lead=0.12)) == UpgradeFilters(can_pop_lead=True)


def test_round_score_all_base() -> None:
    assert round_score(0.5, 30.0, 20.0, 3.0, 3000) == pytest.approx(0.015, rel=1e-6)


def test_round_score_no_moab() -> None:
    assert round_score(0.0, 30.0, 20.0, 3.0, 3000) == pytest.approx(0.02, rel=1e-6)


def test_round_score_all_moab() -> None:
    assert round_score(1.0, 30.0, 20.0, 3.0, 3000) == pytest.approx(0.01, rel=1e-6)


def test_round_score_missing_moab_dps() -> None:
    assert round_score(0.5, None, 20.0, 3.0, 3000) is None


def test_round_score_missing_dps() -> None:
    assert round_score(0.5, 30.0, None, 3.0, 3000) is None


def test_round_score_missing_effective_pierce() -> None:
    assert round_score(0.5, 30.0, 20.0, None, 3000) is None


def test_round_score_zero_cost() -> None:
    assert round_score(0.5, 30.0, 20.0, 3.0, 0) is None


def test_round_score_missing_cost() -> None:
    assert round_score(0.5, 30.0, 20.0, 3.0, None) is None


def test_round_score_zero_weight_ignores_missing_moab() -> None:
    assert round_score(0.0, None, 20.0, 3.0, 3000) == pytest.approx(0.02, rel=1e-6)


@pytest.mark.parametrize("missing", [(None, 3.0), (20.0, None), (None, None)])
def test_round_score_zero_weight_ignores_missing_pierce_terms(
    missing: tuple[float | None, float | None],
) -> None:
    assert round_score(1.0, 30.0, *missing, 3000) == pytest.approx(0.01, rel=1e-6)


def test_round_score_uses_effective_pierce_not_raw() -> None:
    capped = round_score(0.0, 30.0, 20.0, 1.83, 3000)
    assert capped == pytest.approx(20.0 * 1.83 / 3000, rel=1e-6)


HIGH_PIERCE_DPS = 12.0
LOW_PIERCE_DPS = 15.0


def test_reasons_for_all_base() -> None:
    assert reasons_for(make_threats(), 10, HIGH_PIERCE_DPS, 5) == ("affordable", "high_pierce")


def test_reasons_for_camo() -> None:
    result = reasons_for(make_threats(camo_share=0.2), 10, HIGH_PIERCE_DPS, 5)
    assert result == ("affordable", "hits_camo", "high_pierce")


def test_reasons_for_lead() -> None:
    result = reasons_for(make_threats(lead=0.12), 10, HIGH_PIERCE_DPS, 5)
    assert result == ("affordable", "pops_lead", "high_pierce")


def test_reasons_for_single_target() -> None:
    result = reasons_for(make_threats(moab_share=1.0), 10, HIGH_PIERCE_DPS, 5)
    assert result == ("affordable", "high_single_target")


def test_reasons_for_equal_terms() -> None:
    result = reasons_for(make_threats(moab_share=0.5), 60, HIGH_PIERCE_DPS, 5)
    assert result == ("affordable",)


def test_reasons_for_low_effective_pierce() -> None:
    assert reasons_for(make_threats(), 10, LOW_PIERCE_DPS, 4) == ("affordable",)


def test_reasons_for_effective_pierce_just_below_threshold() -> None:
    assert reasons_for(make_threats(), 10, 100.0, 4.999) == ("affordable",)


def test_reasons_for_missing_effective_pierce() -> None:
    assert reasons_for(make_threats(), 10, HIGH_PIERCE_DPS, None) == ("affordable",)


def test_reasons_for_missing_moab_dps_keeps_pierce() -> None:
    result = reasons_for(make_threats(moab_share=0.5), None, 0.2, 5)
    assert "high_pierce" in result


def test_reasons_for_missing_dps_keeps_single_target() -> None:
    result = reasons_for(make_threats(moab_share=0.5), 0.5, None, 5)
    assert result == ("affordable", "high_single_target")


def test_sort_key_zero_score_before_missing() -> None:
    scored = make_recommendation(0.0, 500)
    unscored = make_recommendation(None, 100)
    assert sorted([unscored, scored], key=sort_key) == [scored, unscored]


def test_sort_key_non_leaker_before_leaker_with_higher_score() -> None:
    leaker = make_recommendation(9.0, 100, first_leak_round=24)
    steady = make_recommendation(0.1, 900)
    assert sorted([leaker, steady], key=sort_key) == [steady, leaker]


def test_sort_key_non_leaker_with_missing_score_before_leaker() -> None:
    leaker = make_recommendation(9.0, 100, first_leak_round=24)
    unscored = make_recommendation(None, 900)
    assert sorted([leaker, unscored], key=sort_key) == [unscored, leaker]


def test_sort_key_leakers_ordered_by_score() -> None:
    lower_score = make_recommendation(1.0, 100, first_leak_round=24)
    higher_score = make_recommendation(2.0, 900, first_leak_round=99)
    assert sorted([lower_score, higher_score], key=sort_key) == [higher_score, lower_score]
