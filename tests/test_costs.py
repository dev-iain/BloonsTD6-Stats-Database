from __future__ import annotations

import sqlite3

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.costs import total_cost
from btd6.db import connect
from btd6.db.cost_loader import load_costs
from btd6.db.loader import ensure_tower
from btd6.db.seed import initialize_database
from btd6.query import QueryError
from tests.factories import CostsFactory, UpgradeCostRowFactory, super_monkey_costs

DIFFICULTIES = ("easy", "medium", "hard", "impoppable")


@pytest.fixture
def loaded(database: sqlite3.Connection) -> sqlite3.Connection:
    load_costs(database, "Super Monkey", super_monkey_costs())
    return database


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("0-0-0", 2500),
        ("1-0-0", 4500),
        ("5-0-0", 627000),
        ("0-2-4", 71255),
        ("0-0-4", 67855),
        ("2-2-0", 2500 + 2000 + 2500 + 1500 + 1900),
    ],
)
def test_total_cost_medium(loaded: sqlite3.Connection, path: str, expected: int) -> None:
    assert total_cost(loaded, "Super Monkey", path) == expected


@pytest.mark.parametrize(
    ("difficulty", "path", "expected"),
    [
        ("easy", "0-0-0", 2125),
        ("easy", "1-0-0", 3825),
        ("easy", "0-0-4", 57680),
        ("medium", "0-0-4", 67855),
        ("hard", "0-0-0", 2700),
        ("hard", "1-0-0", 4860),
        ("hard", "0-0-4", 73285),
        ("impoppable", "0-0-0", 3000),
        ("impoppable", "1-0-0", 5400),
        ("impoppable", "0-0-4", 81425),
    ],
)
def test_total_cost_difficulty(
    loaded: sqlite3.Connection, difficulty: str, path: str, expected: int
) -> None:
    assert total_cost(loaded, "Super Monkey", path, difficulty) == expected


def test_total_cost_default_is_medium(loaded: sqlite3.Connection) -> None:
    assert total_cost(loaded, "Super Monkey", "1-0-0") == total_cost(
        loaded, "Super Monkey", "1-0-0", difficulty="medium"
    )


def assert_query_error(
    connection: sqlite3.Connection,
    path: str,
    difficulty: str = "medium",
    tower: str = "Super Monkey",
) -> None:
    with pytest.raises(QueryError):
        total_cost(connection, tower, path, difficulty)


@pytest.mark.parametrize("path", ["3-3-0", "0-3-3", "4-0-4", "5-5-0", "1-2-3"])
def test_total_cost_two_paths_above_tier_two(loaded: sqlite3.Connection, path: str) -> None:
    assert_query_error(loaded, path)


@pytest.mark.parametrize(
    "path", ["1-0", "1-0-0-0", "", "a-b-c", "1--0", "-1-0-0", "1-0-x", " 1-0-0", "100", "1.0-0-0"]
)
def test_total_cost_malformed_path(loaded: sqlite3.Connection, path: str) -> None:
    assert_query_error(loaded, path)


@pytest.mark.parametrize("path", ["6-0-0", "0-6-0", "0-0-6", "9-0-0", "10-0-0"])
def test_total_cost_tier_above_five(loaded: sqlite3.Connection, path: str) -> None:
    assert_query_error(loaded, path)


@pytest.mark.parametrize("path", ["1-1-1", "2-2-2", "5-1-1", "1-1-2"])
def test_total_cost_three_paths(loaded: sqlite3.Connection, path: str) -> None:
    assert_query_error(loaded, path)


@pytest.mark.parametrize("path", ["2-2-0", "0-2-2", "5-2-0", "0-5-2", "2-0-5", "0-0-5"])
def test_total_cost_valid_crosspaths_accepted(loaded: sqlite3.Connection, path: str) -> None:
    assert total_cost(loaded, "Super Monkey", path) >= 2500


@pytest.mark.parametrize("difficulty", ["nightmare", "", "Medium", "EASY", "chimps"])
def test_total_cost_unknown_difficulty(loaded: sqlite3.Connection, difficulty: str) -> None:
    assert_query_error(loaded, "0-0-0", difficulty)


def test_total_cost_unknown_tower(loaded: sqlite3.Connection) -> None:
    assert_query_error(loaded, "0-0-0", tower="Dart Monkey")


def test_total_cost_costs_not_loaded(database: sqlite3.Connection) -> None:
    with database:
        ensure_tower(database, "Super Monkey", "Magic")
    assert total_cost(database, "Super Monkey", "0-0-0") is None
    assert total_cost(database, "Super Monkey", "1-0-0", "hard") is None


def test_total_cost_missing_tier_row_raises(database: sqlite3.Connection) -> None:
    partial = CostsFactory.build(
        base_cost=100, upgrades=[UpgradeCostRowFactory.build(path=1, tier=1)]
    )
    load_costs(database, "Super Monkey", partial)
    assert_query_error(database, "0-0-2")


def test_total_cost_validates_path_even_with_other_difficulty(loaded: sqlite3.Connection) -> None:
    assert_query_error(loaded, "3-3-0", "easy")


def test_total_cost_rounds_each_price_not_total(database: sqlite3.Connection) -> None:
    upgrades = [UpgradeCostRowFactory.build(path=1, tier=1, cost=105)]
    load_costs(database, "Super Monkey", CostsFactory.build(base_cost=100, upgrades=upgrades))
    assert total_cost(database, "Super Monkey", "1-0-0", "hard") == 110 + 115


def is_valid_upgrade_path(tiers: tuple[int, int, int]) -> bool:
    nonzero = [tier for tier in tiers if tier > 0]
    return len(nonzero) <= 2 and sum(tier > 2 for tier in tiers) <= 1


valid_paths = (
    st.tuples(st.integers(0, 5), st.integers(0, 5), st.integers(0, 5))
    .filter(is_valid_upgrade_path)
    .map(lambda parts: "-".join(map(str, parts)))
)


@settings(deadline=None, max_examples=30)
@given(path=valid_paths)
def test_total_cost_properties(path: str) -> None:
    connection = connect(":memory:")
    initialize_database(connection)
    load_costs(connection, "Super Monkey", super_monkey_costs())
    prices = {name: total_cost(connection, "Super Monkey", path, name) for name in DIFFICULTIES}
    connection.close()
    assert all(price % 5 == 0 for price in prices.values())
    assert prices["easy"] <= prices["medium"] <= prices["hard"] <= prices["impoppable"]
    assert prices["medium"] >= 2500


@settings(deadline=None, max_examples=30)
@given(tier=st.integers(0, 4), path_index=st.integers(0, 2))
def test_total_cost_monotonic_in_tier(tier: int, path_index: int) -> None:
    connection = connect(":memory:")
    initialize_database(connection)
    load_costs(connection, "Super Monkey", super_monkey_costs())
    lower, higher = [0, 0, 0], [0, 0, 0]
    lower[path_index], higher[path_index] = tier, tier + 1
    cost_low = total_cost(connection, "Super Monkey", "-".join(map(str, lower)))
    cost_high = total_cost(connection, "Super Monkey", "-".join(map(str, higher)))
    connection.close()
    assert cost_high > cost_low


def test_total_cost_base_tower(loaded: sqlite3.Connection) -> None:
    assert total_cost(loaded, "Super Monkey", "0-0-0") == 2500


def test_total_cost_hard_rounds_each_price(loaded: sqlite3.Connection) -> None:
    assert total_cost(loaded, "Super Monkey", "0-0-4", "hard") == 73285


def test_total_cost_all_base(loaded: sqlite3.Connection) -> None:
    assert total_cost(loaded, "Super Monkey", "1-0-0") == 4500


def test_total_cost_tier_five(loaded: sqlite3.Connection) -> None:
    assert total_cost(loaded, "Super Monkey", "5-0-0") == 627000


def test_total_cost_crosspath(loaded: sqlite3.Connection) -> None:
    assert total_cost(loaded, "Super Monkey", "0-2-4") == 71255


@pytest.mark.parametrize(
    ("difficulty", "expected"), [("easy", 3825), ("hard", 4860), ("impoppable", 5400)]
)
def test_total_cost_each_difficulty(
    loaded: sqlite3.Connection, difficulty: str, expected: int
) -> None:
    assert total_cost(loaded, "Super Monkey", "1-0-0", difficulty) == expected
