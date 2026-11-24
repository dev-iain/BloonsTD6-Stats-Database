from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import FrozenInstanceError

import pytest

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
from btd6.threats import PROPERTY_NAMES, RoundThreats
from tests.factories import CostsFactory, UpgradeRowFactory
from tests.recommend_fixture import (
    build_recommend_database,
    camo_specs,
    load_round_data,
)
from tests.test_ranking import (
    NULL_RATE_STATS,
    UPGRADE_STATS,
    build_database,
    insert_upgrade_rows,
)

BASE_PATHS = ["3-0-0", "0-0-4", "1-0-0", "0-0-0"]
BASE_SCORES = [600 / 27000, (2 / 0.0225 * 8) / 67855, (1 / 0.045 * 2) / 4500, (1 / 0.045) / 2500]
BIG_BUDGET = 100000


@pytest.fixture
def recommend_database() -> Iterator[sqlite3.Connection]:
    connection = build_recommend_database()
    yield connection
    connection.close()


def paths_of(results: list[Recommendation]) -> list[str]:
    return [result.path for result in results]


def cost_of(results: list[Recommendation], path: str) -> int:
    return next(result.total_cost for result in results if result.path == path)


def make_threats(
    camo_share: float = 0.0, lead: float = 0.0, moab_share: float = 0.0
) -> RoundThreats:
    shares = {name: 0.0 for name in PROPERTY_NAMES}
    shares["lead"] = lead
    return RoundThreats(
        round=1,
        total_rbe=100,
        unknown_groups=0,
        property_share=shares,
        camo_share=camo_share,
        regrow_share=0.0,
        moab_share=moab_share,
        mean_layers=1.0,
    )


def test_constants() -> None:
    assert MIN_PROPERTY_SHARE == 0.05
    assert HIGH_PIERCE == 5


# region recommend


def test_recommend_all_base(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 1, BIG_BUDGET)
    assert paths_of(results) == BASE_PATHS
    assert [result.score for result in results] == pytest.approx(BASE_SCORES, rel=1e-6)


def test_recommend_money_equal_to_cost(recommend_database: sqlite3.Connection) -> None:
    assert paths_of(recommend(recommend_database, 1, 4500)) == ["1-0-0", "0-0-0"]


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
    results = recommend(recommend_database, 40, BIG_BUDGET)
    assert paths_of(results) == ["0-0-0", "1-0-0", "3-0-0", "0-0-4"]
    assert all(result.reasons[-1] == "high_single_target" for result in results)


def test_recommend_lead_round(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 63, BIG_BUDGET)
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
    plain = paths_of(recommend(recommend_database, 1, BIG_BUDGET))
    moab = paths_of(recommend(recommend_database, 40, BIG_BUDGET))
    assert plain.index("1-0-0") < plain.index("0-0-0")
    assert moab.index("1-0-0") > moab.index("0-0-0")


def test_recommend_returns_recommendations(recommend_database: sqlite3.Connection) -> None:
    results = recommend(recommend_database, 63, BIG_BUDGET)
    assert results
    for result in results:
        assert isinstance(result, Recommendation)
        assert isinstance(result.reasons, tuple)
        assert result.reasons[0] == "affordable"
        assert result.tower_name == "Super Monkey"
    with pytest.raises(FrozenInstanceError):
        results[0].score = 0.0  # type: ignore[misc]


def test_recommend_fields_match_worked_example(recommend_database: sqlite3.Connection) -> None:
    top = recommend(recommend_database, 63, BIG_BUDGET)[0]
    assert (top.path, top.total_cost) == ("3-0-0", 27000)
    assert top.dps == pytest.approx(100, rel=1e-6)
    assert top.moab_dps == pytest.approx(100, rel=1e-6)
    assert top.pierce_weighted_dps == pytest.approx(600, rel=1e-6)
    assert top.projectile_pierce == pytest.approx(6, rel=1e-6)


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
    for field in ("dps", "moab_dps", "pierce_weighted_dps", "projectile_pierce"):
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
    assert round_score(0.5, 30.0, 60.0, 3000) == pytest.approx(0.015, rel=1e-6)


def test_round_score_no_moab() -> None:
    assert round_score(0.0, 30.0, 60.0, 3000) == pytest.approx(0.02, rel=1e-6)


def test_round_score_all_moab() -> None:
    assert round_score(1.0, 30.0, 60.0, 3000) == pytest.approx(0.01, rel=1e-6)


def test_round_score_missing_moab_dps() -> None:
    assert round_score(0.5, None, 60.0, 3000) is None


def test_round_score_missing_pierce_dps() -> None:
    assert round_score(0.5, 30.0, None, 3000) is None


def test_round_score_zero_cost() -> None:
    assert round_score(0.5, 30.0, 60.0, 0) is None


def test_round_score_missing_cost() -> None:
    assert round_score(0.5, 30.0, 60.0, None) is None


def test_round_score_zero_weight_ignores_missing_moab() -> None:
    assert round_score(0.0, None, 60.0, 3000) == pytest.approx(0.02, rel=1e-6)


def test_round_score_zero_weight_ignores_missing_pierce() -> None:
    assert round_score(1.0, 30.0, None, 3000) == pytest.approx(0.01, rel=1e-6)


def test_reasons_for_all_base() -> None:
    assert reasons_for(make_threats(), 10, 60, 5) == ("affordable", "high_pierce")


def test_reasons_for_camo() -> None:
    result = reasons_for(make_threats(camo_share=0.2), 10, 60, 5)
    assert result == ("affordable", "hits_camo", "high_pierce")


def test_reasons_for_lead() -> None:
    result = reasons_for(make_threats(lead=0.12), 10, 60, 5)
    assert result == ("affordable", "pops_lead", "high_pierce")


def test_reasons_for_single_target() -> None:
    result = reasons_for(make_threats(moab_share=1.0), 10, 60, 5)
    assert result == ("affordable", "high_single_target")


def test_reasons_for_equal_terms() -> None:
    assert reasons_for(make_threats(moab_share=0.5), 60, 60, 5) == ("affordable",)


def test_reasons_for_low_pierce() -> None:
    assert reasons_for(make_threats(), 10, 60, 4) == ("affordable",)


def test_reasons_for_missing_pierce() -> None:
    assert reasons_for(make_threats(), 10, 60, None) == ("affordable",)


def test_reasons_for_missing_moab_dps_keeps_pierce() -> None:
    result = reasons_for(make_threats(moab_share=0.5), None, 0.5, 5)
    assert "high_pierce" in result


def test_reasons_for_missing_pierce_dps_keeps_single_target() -> None:
    result = reasons_for(make_threats(moab_share=0.5), 0.5, None, 5)
    assert result == ("affordable", "high_single_target")


def make_recommendation(score: float | None, total_cost: int) -> Recommendation:
    return Recommendation("Super Monkey", "0-0-0", total_cost, score, None, None, None, None, ())


def test_sort_key_zero_score_before_missing() -> None:
    scored = make_recommendation(0.0, 500)
    unscored = make_recommendation(None, 100)
    assert sorted([unscored, scored], key=sort_key) == [scored, unscored]
