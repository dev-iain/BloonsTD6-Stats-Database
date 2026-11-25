from __future__ import annotations

import dataclasses
import sqlite3
from collections.abc import Iterator

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.query import QueryError, UpgradeFilters
from btd6.recommend import (
    OwnedTower,
    Recommendation,
    filters_for_threats,
    recommend,
    sort_key,
)
from tests.recommend_fixture import (
    MEDIUM_COSTS,
    build_full_database,
    build_recommend_database,
    fixture_value,
    make_recommendation,
    make_threats,
    reachable_paths,
    upgrade_price,
    upgrade_window_score,
)

BIG_BUDGET = 100000
EARLY_BUDGET = 5000
SUPER = "Super Monkey"
RECOMMENDATION_FIELDS = [
    "tower_name",
    "path",
    "total_cost",
    "upgrade_from",
    "score",
    "dps",
    "moab_dps",
    "pierce_weighted_dps",
    "projectile_pierce",
    "effective_pierce",
    "first_leak_round",
    "reasons",
]


@pytest.fixture(scope="module")
def database() -> Iterator[sqlite3.Connection]:
    connection = build_recommend_database()
    yield connection
    connection.close()


@pytest.fixture
def full_database(offline_costs_wiki: None) -> Iterator[sqlite3.Connection]:
    connection = build_full_database()
    yield connection
    connection.close()


def own(*paths: str, tower: str = SUPER) -> list[OwnedTower]:
    return [OwnedTower(tower, path) for path in paths]


def upgrades_of(results: list[Recommendation]) -> dict[tuple[str, str], Recommendation]:
    return {
        (result.upgrade_from, result.path): result
        for result in results
        if result.upgrade_from is not None
    }


def purchases_of(results: list[Recommendation]) -> dict[str, Recommendation]:
    return {result.path: result for result in results if result.upgrade_from is None}


def first_per_tower(results: list[Recommendation]) -> list[Recommendation]:
    seen: set[str] = set()
    kept = []
    for result in results:
        if result.tower_name not in seen:
            seen.add(result.tower_name)
            kept.append(result)
    return kept


# region owned towers


def test_owned_tower_is_a_named_tuple() -> None:
    owned = OwnedTower("Ninja Monkey", "0-0-0")
    assert tuple(owned) == ("Ninja Monkey", "0-0-0")
    assert (owned.tower_name, owned.path) == ("Ninja Monkey", "0-0-0")


def test_recommendation_fields_put_upgrade_from_after_total_cost() -> None:
    assert [field.name for field in dataclasses.fields(Recommendation)] == RECOMMENDATION_FIELDS


def test_recommendation_upgrade_from_is_required_keyword_or_positional() -> None:
    result = make_recommendation(1.0, 100, upgrade_from="0-0-0")
    assert result.upgrade_from == "0-0-0"
    assert result.score == 1.0


def test_sort_key_new_purchase_before_upgrade_on_full_tie() -> None:
    upgrade = make_recommendation(1.0, 100, upgrade_from="0-0-0")
    purchase = make_recommendation(1.0, 100)
    assert sorted([upgrade, purchase], key=sort_key) == [purchase, upgrade]


def test_sort_key_cost_is_the_price_paid_for_an_upgrade() -> None:
    cheap_upgrade = make_recommendation(1.0, 100, upgrade_from="0-0-0")
    pricey_purchase = make_recommendation(1.0, 200)
    assert sorted([pricey_purchase, cheap_upgrade], key=sort_key) == [
        cheap_upgrade,
        pricey_purchase,
    ]


def test_sort_key_negative_score_after_positive_before_missing() -> None:
    positive = make_recommendation(0.5, 100)
    negative = make_recommendation(-0.5, 100)
    missing = make_recommendation(None, 100)
    assert sorted([missing, negative, positive], key=sort_key) == [positive, negative, missing]


@pytest.mark.parametrize(
    ("covered", "camo", "lead"),
    [
        ((), True, True),
        (("camo",), None, True),
        (("lead",), True, None),
        (("camo", "lead"), None, None),
    ],
    ids=["nothing_covered", "camo_covered", "lead_covered", "both_covered"],
)
def test_filters_for_threats_drops_covered_needs(
    covered: tuple[str, ...], camo: bool | None, lead: bool | None
) -> None:
    threats = make_threats(camo_share=0.2, lead=0.2)
    filters = filters_for_threats(threats, set(covered))
    assert filters == UpgradeFilters(can_hit_camo=camo, can_pop_lead=lead)


@pytest.mark.parametrize("path", ["1-2", "6-0-0", "abc", "", "1-0-0-0", "-1-0-0", "0-0-6", "x-0-0"])
def test_recommend_owned_path_must_be_x_y_z(database: sqlite3.Connection, path: str) -> None:
    with pytest.raises(QueryError) as caught:
        recommend(database, 1, BIG_BUDGET, owned=[OwnedTower(SUPER, path)])
    assert str(caught.value) == f"owned path must be X-Y-Z, got {path!r}"


def test_recommend_owned_path_checked_for_unknown_tower(database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError, match="owned path must be X-Y-Z, got '1-2'"):
        recommend(database, 1, BIG_BUDGET, owned=[OwnedTower("Banana Farm", "1-2")])


def test_recommend_owned_checks_every_entry(database: sqlite3.Connection) -> None:
    owned = [OwnedTower(SUPER, "0-0-0"), OwnedTower(SUPER, "1-2")]
    with pytest.raises(QueryError, match="got '1-2'"):
        recommend(database, 1, BIG_BUDGET, owned=owned)


@pytest.mark.parametrize(
    "entry",
    [
        OwnedTower("Banana Farm", "2-0-0"),
        OwnedTower("Ninja Monkey", "0-0-4"),
        OwnedTower(SUPER, "2-0-0"),
        OwnedTower(SUPER, "5-5-5"),
    ],
    ids=["unknown_tower", "tower_not_in_database", "impossible_crosspath", "no_row"],
)
def test_recommend_owned_unknown_entry_is_ignored(
    database: sqlite3.Connection, entry: OwnedTower
) -> None:
    baseline = recommend(database, 22, BIG_BUDGET)
    assert recommend(database, 22, BIG_BUDGET, owned=[entry]) == baseline


@pytest.mark.parametrize("owned", [None, (), []], ids=["none", "tuple", "list"])
def test_recommend_owned_nothing_is_the_same_as_default(
    database: sqlite3.Connection, owned: object
) -> None:
    results = recommend(database, 1, BIG_BUDGET, owned=owned)
    assert results == recommend(database, 1, BIG_BUDGET)
    assert {result.upgrade_from for result in results} == {None}
    assert all("upgrades_owned" not in result.reasons for result in results)


@pytest.mark.parametrize("owned_path", list(MEDIUM_COSTS))
def test_recommend_owned_candidate_set(database: sqlite3.Connection, owned_path: str) -> None:
    results = recommend(database, 1, BIG_BUDGET, horizon=1, owned=own(owned_path))
    upgrades = upgrades_of(results)
    assert {path for _, path in upgrades} == set(reachable_paths(owned_path))
    assert {origin for origin, _ in upgrades} <= {owned_path}
    for (_, path), result in upgrades.items():
        assert result.tower_name == SUPER
        assert result.total_cost == upgrade_price(owned_path, path)
        assert isinstance(result.total_cost, int)


def test_recommend_owned_expected_candidate_sets(database: sqlite3.Connection) -> None:
    assert reachable_paths("0-0-0") == ["1-0-0", "3-0-0", "0-0-4"]
    assert reachable_paths("1-0-0") == ["3-0-0"]
    assert reachable_paths("3-0-0") == []
    assert reachable_paths("0-0-4") == []


def test_recommend_owned_new_purchases_are_still_offered(database: sqlite3.Connection) -> None:
    results = recommend(database, 1, BIG_BUDGET, horizon=1, owned=own("0-0-0"))
    purchases = purchases_of(results)
    assert set(purchases) == set(MEDIUM_COSTS)
    assert {path: result.total_cost for path, result in purchases.items()} == MEDIUM_COSTS
    assert all("upgrades_owned" not in result.reasons for result in purchases.values())


def test_recommend_owned_upgrade_reasons_and_fields(database: sqlite3.Connection) -> None:
    results = recommend(database, 63, BIG_BUDGET, horizon=1, owned=own("0-0-0"))
    upgrade = upgrades_of(results)[("0-0-0", "3-0-0")]
    purchase = purchases_of(results)["3-0-0"]
    assert upgrade.upgrade_from == "0-0-0"
    assert upgrade.total_cost == 24500
    assert upgrade.reasons == ("affordable", "upgrades_owned", "pops_lead", "high_pierce")
    assert purchase.reasons == ("affordable", "pops_lead", "high_pierce")
    for field in (
        "dps",
        "moab_dps",
        "pierce_weighted_dps",
        "projectile_pierce",
        "effective_pierce",
    ):
        assert getattr(upgrade, field) == getattr(purchase, field)


def test_recommend_owned_upgrade_must_pass_round_filters(database: sqlite3.Connection) -> None:
    results = recommend(database, 63, BIG_BUDGET, horizon=1, owned=own("0-0-0"))
    assert set(upgrades_of(results)) == {("0-0-0", "3-0-0"), ("0-0-0", "0-0-4")}


def test_recommend_owned_camo_round_upgrade_must_hit_camo(database: sqlite3.Connection) -> None:
    results = recommend(database, 101, BIG_BUDGET, horizon=1, owned=own("0-0-0"))
    assert set(upgrades_of(results)) == {("0-0-0", "0-0-4")}
    assert upgrades_of(results)[("0-0-0", "0-0-4")].reasons[:3] == (
        "affordable",
        "upgrades_owned",
        "hits_camo",
    )


@pytest.mark.parametrize(
    ("money", "expected"),
    [(1999, []), (2000, ["1-0-0"]), (24499, ["1-0-0"]), (24500, ["1-0-0", "3-0-0"])],
)
def test_recommend_owned_affordability_uses_price(
    database: sqlite3.Connection, money: int, expected: list[str]
) -> None:
    results = recommend(database, 1, money, horizon=1, owned=own("0-0-0"))
    upgrades = [result for result in results if result.upgrade_from is not None]
    assert sorted(result.path for result in upgrades) == expected
    assert all(result.total_cost <= money for result in results)


def test_recommend_owned_money_below_every_price(database: sqlite3.Connection) -> None:
    assert recommend(database, 1, 1999, owned=own("0-0-0")) == []


def test_recommend_owned_price_follows_difficulty(database: sqlite3.Connection) -> None:
    results = recommend(database, 1, BIG_BUDGET, "hard", horizon=1, owned=own("0-0-0"))
    assert upgrades_of(results)[("0-0-0", "3-0-0")].total_cost == 29160 - 2700


def test_recommend_owned_duplicates_give_one_set_of_candidates(
    database: sqlite3.Connection,
) -> None:
    single = recommend(database, 1, BIG_BUDGET, owned=own("0-0-0"))
    repeated = recommend(database, 1, BIG_BUDGET, owned=own("0-0-0", "0-0-0", "0-0-0"))
    assert repeated == single


def test_recommend_owned_two_paths_give_two_candidates_for_one_upgrade(
    database: sqlite3.Connection,
) -> None:
    results = recommend(database, 1, BIG_BUDGET, horizon=1, owned=own("0-0-0", "1-0-0"))
    upgrades = upgrades_of(results)
    assert upgrades[("0-0-0", "3-0-0")].total_cost == 24500
    assert upgrades[("1-0-0", "3-0-0")].total_cost == 22500
    assert ("1-0-0", "1-0-0") not in upgrades


def test_recommend_owned_order_does_not_matter(database: sqlite3.Connection) -> None:
    forward = recommend(database, 26, BIG_BUDGET, owned=own("0-0-0", "1-0-0"))
    backward = recommend(database, 26, BIG_BUDGET, owned=own("1-0-0", "0-0-0"))
    assert forward == backward


@pytest.mark.parametrize(
    ("owned_path", "start", "horizon"),
    [
        ("0-0-0", 1, 1),
        ("0-0-0", 1, 4),
        ("1-0-0", 20, 4),
        ("0-0-0", 26, 3),
        ("1-0-0", 26, 3),
        ("0-0-0", 63, 1),
    ],
    ids=["round_1", "window_1_4", "from_1_0_0", "lead_leak_window", "leak_from_1_0_0", "lead_now"],
)
def test_recommend_owned_score_is_decay_weighted_mean_of_value_gain_per_price(
    database: sqlite3.Connection, owned_path: str, start: int, horizon: int
) -> None:
    results = recommend(database, start, BIG_BUDGET, horizon=horizon, owned=own(owned_path))
    upgrades = upgrades_of(results)
    assert upgrades
    for (_, path), result in upgrades.items():
        expected = upgrade_window_score(owned_path, path, start, horizon)
        assert result.score == pytest.approx(expected, rel=1e-6, abs=1e-12)


def test_recommend_owned_score_uses_zero_value_for_owned_with_unmet_need(
    database: sqlite3.Connection,
) -> None:
    assert fixture_value("0-0-0", 63) == 0.0
    results = recommend(database, 63, BIG_BUDGET, horizon=1, owned=own("0-0-0"))
    upgrade = upgrades_of(results)[("0-0-0", "3-0-0")]
    assert upgrade.score == pytest.approx(fixture_value("3-0-0", 63) / 24500, rel=1e-6)


def test_recommend_owned_upgrade_leaks_when_a_later_round_needs_more(
    database: sqlite3.Connection,
) -> None:
    results = recommend(database, 26, BIG_BUDGET, horizon=3, owned=own("0-0-0"))
    upgrades = upgrades_of(results)
    assert upgrades[("0-0-0", "1-0-0")].first_leak_round == 28
    assert upgrades[("0-0-0", "1-0-0")].reasons[-1] == "fails_lead_at_28"
    assert upgrades[("0-0-0", "3-0-0")].first_leak_round is None
    assert results.index(upgrades[("0-0-0", "1-0-0")]) > results.index(upgrades[("0-0-0", "0-0-4")])


def test_recommend_owned_score_zero_gain_in_a_moab_round(database: sqlite3.Connection) -> None:
    results = recommend(database, 40, BIG_BUDGET, horizon=1, owned=own("0-0-0"))
    assert upgrades_of(results)[("0-0-0", "1-0-0")].score == pytest.approx(0.0, abs=1e-12)


def reasons_union(results: list[Recommendation]) -> set[str]:
    return {reason for result in results for reason in result.reasons}


def test_recommend_owned_camo_covered_makes_every_upgrade_eligible(
    database: sqlite3.Connection,
) -> None:
    alone = recommend(database, 101, BIG_BUDGET, horizon=1)
    covered = recommend(database, 101, BIG_BUDGET, horizon=1, owned=own("0-0-4"))
    assert [result.path for result in alone] == ["0-0-4"]
    assert {result.path for result in covered} == set(MEDIUM_COSTS)
    assert "hits_camo" in reasons_union(alone)
    assert "hits_camo" not in reasons_union(covered)


def test_recommend_owned_camo_not_covered_by_a_tower_that_cannot_hit_it(
    database: sqlite3.Connection,
) -> None:
    results = recommend(database, 101, BIG_BUDGET, horizon=1, owned=own("3-0-0"))
    assert {result.path for result in purchases_of(results).values()} == {"0-0-4"}
    assert "hits_camo" in reasons_union(results)


def test_recommend_owned_lead_covered_drops_the_lead_filter(database: sqlite3.Connection) -> None:
    results = recommend(database, 63, BIG_BUDGET, horizon=1, owned=own("3-0-0"))
    assert set(purchases_of(results)) == set(MEDIUM_COSTS)
    assert "pops_lead" not in reasons_union(results)


def test_recommend_owned_covers_one_need_and_keeps_the_other(
    database: sqlite3.Connection,
) -> None:
    alone = recommend(database, 37, BIG_BUDGET, horizon=1)
    covered = recommend(database, 37, BIG_BUDGET, horizon=1, owned=own("3-0-0"))
    assert {result.path for result in alone} == {"0-0-4"}
    assert {result.path for result in covered} == {"0-0-4"}
    assert alone[0].reasons[:3] == ("affordable", "hits_camo", "pops_lead")
    assert covered[0].reasons[:2] == ("affordable", "hits_camo")
    assert "pops_lead" not in covered[0].reasons


def test_recommend_owned_camo_covered_removes_later_leaks(database: sqlite3.Connection) -> None:
    alone = recommend(database, 22, BIG_BUDGET, horizon=3)
    covered = recommend(database, 22, BIG_BUDGET, horizon=3, owned=own("0-0-4"))
    assert {result.first_leak_round for result in alone} == {24, None}
    assert "fails_camo_at_24" in reasons_union(alone)
    assert {result.first_leak_round for result in covered} == {None}
    assert not any(reason.startswith("fails_") for reason in reasons_union(covered))


def test_recommend_owned_lead_covered_removes_later_leaks(database: sqlite3.Connection) -> None:
    alone = recommend(database, 26, BIG_BUDGET, horizon=3)
    covered = recommend(database, 26, BIG_BUDGET, horizon=3, owned=own("3-0-0"))
    assert "fails_lead_at_28" in reasons_union(alone)
    assert {result.first_leak_round for result in covered} == {None}


def test_recommend_owned_covered_leak_scores_the_value_instead_of_zero(
    database: sqlite3.Connection,
) -> None:
    covered_lead = frozenset({"lead"})
    results = recommend(database, 26, BIG_BUDGET, horizon=3, owned=own("3-0-0"))
    purchase = purchases_of(results)["1-0-0"]
    assert fixture_value("1-0-0", 28, covered_lead) > 0
    assert purchase.first_leak_round is None
    assert purchase.score is not None


def test_recommend_owned_coverage_does_not_change_scores_of_unaffected_rounds(
    database: sqlite3.Connection,
) -> None:
    alone = {result.path: result for result in recommend(database, 1, BIG_BUDGET)}
    covered = purchases_of(recommend(database, 1, BIG_BUDGET, owned=own("0-0-4")))
    assert {path: result.score for path, result in covered.items()} == pytest.approx(
        {path: result.score for path, result in alone.items()}
    )


def test_recommend_owned_other_tower_covers_camo(full_database: sqlite3.Connection) -> None:
    alone = recommend(full_database, 24, EARLY_BUDGET, horizon=1)
    covered = recommend(
        full_database, 24, EARLY_BUDGET, horizon=1, owned=own("0-0-0", tower="Ninja Monkey")
    )
    assert "Dart Monkey" not in {result.tower_name for result in alone}
    dart = [
        result for result in covered if (result.tower_name, result.path) == ("Dart Monkey", "0-0-0")
    ]
    assert len(dart) == 1
    assert "hits_camo" not in dart[0].reasons
    assert "hits_camo" in reasons_union(alone)


def test_recommend_owned_other_tower_removes_camo_leak(full_database: sqlite3.Connection) -> None:
    owned = own("0-0-0", tower="Ninja Monkey")
    alone = recommend(full_database, 22, EARLY_BUDGET, horizon=3)
    covered = recommend(full_database, 22, EARLY_BUDGET, horizon=3, owned=owned)
    assert any(result.tower_name == SUPER and result.first_leak_round == 24 for result in alone)
    assert {result.first_leak_round for result in covered} == {None}
    dart = [result for result in covered if result.tower_name == "Dart Monkey"]
    assert dart
    assert not any("fails_camo_at_24" in result.reasons for result in covered)


def test_recommend_owned_tower_without_the_need_changes_no_purchase(
    full_database: sqlite3.Connection,
) -> None:
    alone = recommend(full_database, 24, EARLY_BUDGET)
    owned = own("0-0-0", tower="Dart Monkey")
    with_owned = recommend(full_database, 24, EARLY_BUDGET, owned=owned)
    assert [result for result in with_owned if result.upgrade_from is None] == alone


@pytest.mark.parametrize("value", ["yes", "true", 1, 0, None, "False"])
def test_recommend_one_per_tower_must_be_a_bool(
    database: sqlite3.Connection, value: object
) -> None:
    with pytest.raises(QueryError) as caught:
        recommend(database, 1, BIG_BUDGET, one_per_tower=value)
    assert str(caught.value) == f"one_per_tower must be true or false, got {value!r}"


def test_recommend_one_per_tower_default_is_false(database: sqlite3.Connection) -> None:
    assert recommend(database, 1, BIG_BUDGET) == recommend(
        database, 1, BIG_BUDGET, one_per_tower=False
    )
    assert len(recommend(database, 1, BIG_BUDGET)) == 4


def test_recommend_one_per_tower_keeps_the_first_result(database: sqlite3.Connection) -> None:
    everything = recommend(database, 1, BIG_BUDGET)
    assert recommend(database, 1, BIG_BUDGET, one_per_tower=True) == everything[:1]


def test_recommend_one_per_tower_upgrade_and_purchase_share_a_tower(
    database: sqlite3.Connection,
) -> None:
    everything = recommend(database, 63, BIG_BUDGET, owned=own("0-0-0"))
    assert len(everything) == 4
    kept = recommend(database, 63, BIG_BUDGET, owned=own("0-0-0"), one_per_tower=True)
    assert kept == everything[:1]


def test_recommend_one_per_tower_applies_before_limit(full_database: sqlite3.Connection) -> None:
    everything = recommend(full_database, 63, BIG_BUDGET)
    names = [result.tower_name for result in everything]
    assert len(names) > len(set(names))
    limited = recommend(full_database, 63, BIG_BUDGET, limit=3, one_per_tower=True)
    assert limited == first_per_tower(everything)[:3]
    assert len({result.tower_name for result in limited}) == 3


def test_recommend_one_per_tower_without_limit_has_unique_names(
    full_database: sqlite3.Connection,
) -> None:
    results = recommend(full_database, 63, BIG_BUDGET, one_per_tower=True)
    names = [result.tower_name for result in results]
    assert len(names) == len(set(names)) > 1
    assert results == first_per_tower(recommend(full_database, 63, BIG_BUDGET))


def test_recommend_one_per_tower_with_owned_towers(full_database: sqlite3.Connection) -> None:
    owned = own("0-0-0", tower="Ninja Monkey") + own("0-0-0", tower="Dart Monkey")
    everything = recommend(full_database, 24, EARLY_BUDGET, owned=owned)
    assert any(result.upgrade_from for result in everything)
    kept = recommend(full_database, 24, EARLY_BUDGET, owned=owned, one_per_tower=True)
    assert kept == first_per_tower(everything)
    assert len({result.tower_name for result in kept}) == len(kept)


def test_recommend_upgrades_only_offered_for_the_owned_tower(
    full_database: sqlite3.Connection,
) -> None:
    owned = own("0-0-0", tower="Ninja Monkey")
    results = recommend(full_database, 24, EARLY_BUDGET, owned=owned)
    upgrades = [result for result in results if result.upgrade_from is not None]
    assert upgrades
    assert {result.tower_name for result in upgrades} == {"Ninja Monkey"}
    assert {result.upgrade_from for result in upgrades} == {"0-0-0"}


def test_recommend_validation_order_horizon_before_owned(database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError, match="horizon must be at least 1, got 0"):
        recommend(database, 150, BIG_BUDGET, horizon=0, owned=own("1-2"), one_per_tower="yes")


def test_recommend_validation_order_owned_before_one_per_tower(
    database: sqlite3.Connection,
) -> None:
    with pytest.raises(QueryError, match="owned path must be X-Y-Z, got '1-2'"):
        recommend(database, 150, BIG_BUDGET, owned=own("1-2"), one_per_tower="yes")


def test_recommend_validation_order_one_per_tower_before_round(
    database: sqlite3.Connection,
) -> None:
    with pytest.raises(QueryError, match="one_per_tower must be true or false, got 'yes'"):
        recommend(database, 150, BIG_BUDGET, one_per_tower="yes")


def test_recommend_validation_order_round_after_owned_ok(database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError, match="Round 150 is not loaded"):
        recommend(database, 150, BIG_BUDGET, owned=own("0-0-0"), one_per_tower=True)


PROPERTY_SETTINGS = settings(max_examples=60, deadline=None)
owned_strategy = st.lists(
    st.builds(
        OwnedTower,
        st.sampled_from([SUPER, "Ninja Monkey"]),
        st.sampled_from([*MEDIUM_COSTS, "2-0-0"]),
    ),
    max_size=4,
)


@PROPERTY_SETTINGS
@given(
    owned=owned_strategy,
    money=st.integers(0, 120000),
    round_number=st.sampled_from([1, 26, 37, 63, 101]),
    horizon=st.integers(1, 4),
    one_per_tower=st.booleans(),
)
def test_recommend_owned_invariants(
    database: sqlite3.Connection,
    owned: list[OwnedTower],
    money: int,
    round_number: int,
    horizon: int,
    one_per_tower: bool,
) -> None:
    results = recommend(
        database, round_number, money, horizon=horizon, owned=owned, one_per_tower=one_per_tower
    )
    owned_paths = {entry.path for entry in owned if entry.tower_name == SUPER}
    for result in results:
        assert result.total_cost <= money
        assert ("upgrades_owned" in result.reasons) == (result.upgrade_from is not None)
        if result.upgrade_from is not None:
            assert result.upgrade_from in owned_paths
            assert result.path in reachable_paths(result.upgrade_from)
            assert result.total_cost == upgrade_price(result.upgrade_from, result.path)
    if one_per_tower:
        assert len(results) <= 1
        everything = recommend(database, round_number, money, horizon=horizon, owned=owned)
        assert results == everything[:1]


@PROPERTY_SETTINGS
@given(owned=owned_strategy, round_number=st.sampled_from([1, 26, 63]))
def test_recommend_owned_is_order_and_duplicate_independent(
    database: sqlite3.Connection, owned: list[OwnedTower], round_number: int
) -> None:
    baseline = recommend(database, round_number, BIG_BUDGET, owned=owned)
    assert (
        recommend(database, round_number, BIG_BUDGET, owned=[*reversed(owned), *owned]) == baseline
    )


# endregion
