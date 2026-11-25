from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

import pandas
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.db import connect
from btd6.db.cost_loader import load_costs
from btd6.db.loader import INSERT_UPGRADE_SQL, UPGRADE_COLUMNS, damage_type_ids, ensure_tower
from btd6.db.seed import initialize_database
from btd6.query import QueryError, UpgradeFilters, search_upgrades
from btd6.ranking import add_metrics, rank_upgrades
from tests.factories import UpgradeRowFactory, super_monkey_costs

BASE_PATHS = ["0-0-0", "1-0-0", "3-0-0", "0-0-4"]
UPGRADE_STATS = {
    "0-0-0": {
        "damage_type": "Sharp",
        "projectile_damage": 1,
        "projectile_count": 1,
        "attack_rate": 0.045,
        "projectile_pierce": 1,
    },
    "1-0-0": {
        "damage_type": "Energy",
        "projectile_damage": 1,
        "projectile_count": 1,
        "attack_rate": 0.045,
        "projectile_pierce": 2,
    },
    "3-0-0": {
        "damage_type": "Plasma",
        "projectile_damage": 1,
        "projectile_count": 3,
        "attack_rate": 0.03,
        "projectile_pierce": 6,
    },
    "0-0-4": {
        "damage_type": "Normal",
        "projectile_damage": 2,
        "projectile_count": 1,
        "attack_rate": 0.0225,
        "projectile_pierce": 8,
    },
}
NULL_RATE_STATS = {
    "damage_type": "Sharp",
    "projectile_damage": 1,
    "projectile_count": 1,
    "attack_rate": None,
    "projectile_pierce": 1,
}
METRICS = ("dps", "moab_dps", "damage_per_dollar", "pierce_damage_per_dollar")
DAMAGE_TYPES = ["Sharp", "Normal", "Plasma", "Energy"]


def insert_upgrade_rows(connection: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    tower_id = ensure_tower(connection, "Super Monkey", "Magic")
    type_ids = damage_type_ids(connection)
    params = [
        (
            tower_id,
            type_ids[row["damage_type"]],
            *[int(row[key]) if isinstance(row[key], bool) else row[key] for key in UPGRADE_COLUMNS],
        )
        for row in rows
    ]
    with connection:
        connection.executemany(INSERT_UPGRADE_SQL, params)
        for row in rows:
            mirror_first_attack(connection, tower_id, row, type_ids[row["damage_type"]])


def mirror_first_attack(
    connection: sqlite3.Connection, tower_id: int, row: dict[str, Any], type_id: int
) -> None:
    upgrade_id = connection.execute(
        "SELECT id FROM upgrades WHERE tower_id = ? AND path = ?", (tower_id, row["path"])
    ).fetchone()[0]
    attack_id = connection.execute(
        "INSERT INTO attacks (upgrade_id, attack_index, name, rate) VALUES (?, 0, 'Attack', ?)",
        (upgrade_id, row["attack_rate"]),
    ).lastrowid
    connection.execute(
        "INSERT INTO projectiles (attack_id, projectile_index, name, damage, pierce, count,"
        " damage_type_id, can_hit_camo) VALUES (?, 0, 'Projectile', ?, ?, ?, ?, ?)",
        (
            attack_id,
            row["projectile_damage"],
            row["projectile_pierce"],
            row["projectile_count"],
            type_id,
            int(row["can_hit_camo"]),
        ),
    )


def build_database(specs: dict[str, dict[str, Any]], with_costs: bool = True) -> sqlite3.Connection:
    connection = connect(":memory:")
    initialize_database(connection)
    insert_upgrade_rows(
        connection, [UpgradeRowFactory.build(path=path, **stats) for path, stats in specs.items()]
    )
    if with_costs:
        load_costs(connection, "Super Monkey", super_monkey_costs())
    return connection


@pytest.fixture
def ranked_database() -> Iterator[sqlite3.Connection]:
    connection = build_database(UPGRADE_STATS)
    yield connection
    connection.close()


def paths_of(frame: pandas.DataFrame) -> list[str]:
    return list(frame["path"])


def value_of(frame: pandas.DataFrame, path: str, column: str) -> float:
    return frame.loc[frame["path"] == path, column].iloc[0]


def metric_frame(**columns: Any) -> pandas.DataFrame:
    base = {
        "upgrade_dps": [22.2222222],
        "upgrade_moab_dps": [30.0],
        "projectile_pierce": [2.0],
        "total_cost": [4500.0],
    }
    base.update(columns)
    return pandas.DataFrame(base)


def test_add_metrics_all_base() -> None:
    result = add_metrics(metric_frame())
    assert result["dps"].iloc[0] == pytest.approx(22.2222222, rel=1e-6)
    assert result["moab_dps"].iloc[0] == pytest.approx(30.0, rel=1e-6)
    assert result["pierce_weighted_dps"].iloc[0] == pytest.approx(44.4444444, rel=1e-6)
    assert result["damage_per_dollar"].iloc[0] == pytest.approx(0.00493827, rel=1e-6)
    assert result["pierce_damage_per_dollar"].iloc[0] == pytest.approx(0.00987654, rel=1e-6)


def test_add_metrics_does_not_mutate_input() -> None:
    frame = metric_frame()
    add_metrics(frame)
    assert "dps" not in frame.columns
    assert "moab_dps" not in frame.columns


def test_add_metrics_keeps_row_order() -> None:
    frame = metric_frame(
        upgrade_dps=[1.0, 2.0, 3.0],
        upgrade_moab_dps=[1.0] * 3,
        projectile_pierce=[1.0] * 3,
        total_cost=[1.0] * 3,
    )
    assert list(add_metrics(frame)["dps"]) == [1.0, 2.0, 3.0]


ALL_METRICS = ["dps", "moab_dps", "pierce_weighted_dps", "damage_per_dollar"]


@pytest.mark.parametrize(
    ("column", "value", "null_columns", "set_columns"),
    [
        ("upgrade_dps", None, ["dps", "pierce_weighted_dps", "damage_per_dollar"], ["moab_dps"]),
        ("upgrade_moab_dps", None, ["moab_dps"], ["dps", "damage_per_dollar"]),
        ("projectile_pierce", None, ["pierce_weighted_dps"], ["dps", "damage_per_dollar"]),
        ("total_cost", None, ["damage_per_dollar"], ["dps", "pierce_weighted_dps"]),
        ("total_cost", 0.0, ["damage_per_dollar"], ["dps", "pierce_weighted_dps"]),
    ],
)
def test_add_metrics_null_and_zero_inputs(
    column: str, value: float | None, null_columns: list[str], set_columns: list[str]
) -> None:
    result = add_metrics(metric_frame(**{column: [value]}))
    for name in null_columns:
        assert pandas.isna(result[name].iloc[0]), name
    for name in set_columns:
        assert not pandas.isna(result[name].iloc[0]), name


def test_add_metrics_non_numeric_dps_is_nan() -> None:
    result = add_metrics(metric_frame(upgrade_dps=["abc"]))
    for name in ("dps", "pierce_weighted_dps", "damage_per_dollar"):
        assert pandas.isna(result[name].iloc[0]), name


def test_add_metrics_ignores_first_projectile_columns() -> None:
    frame = metric_frame(projectile_damage=[99.0], projectile_count=[9.0], attack_rate=[0.001])
    assert add_metrics(frame)["dps"].iloc[0] == pytest.approx(22.2222222, rel=1e-6)


def test_rank_upgrades_all_base(ranked_database: sqlite3.Connection) -> None:
    result = rank_upgrades(ranked_database)
    assert paths_of(result) == ["0-0-0", "1-0-0", "3-0-0", "0-0-4"]
    assert value_of(result, "0-0-0", "damage_per_dollar") == pytest.approx(0.00888889, rel=1e-6)


def test_rank_upgrades_returns_metric_columns(ranked_database: sqlite3.Connection) -> None:
    result = rank_upgrades(ranked_database)
    expected = {
        "total_cost",
        "dps",
        "moab_dps",
        "pierce_weighted_dps",
        "damage_per_dollar",
        "pierce_damage_per_dollar",
        "path",
        "tower_name",
    }
    assert isinstance(result, pandas.DataFrame)
    assert expected <= set(result.columns)


def test_rank_upgrades_dps_tie_by_cost(ranked_database: sqlite3.Connection) -> None:
    result = rank_upgrades(ranked_database, metric="dps")
    assert paths_of(result) == ["3-0-0", "0-0-4", "0-0-0", "1-0-0"]


def test_rank_upgrades_pierce_damage_per_dollar(ranked_database: sqlite3.Connection) -> None:
    result = rank_upgrades(ranked_database, metric="pierce_damage_per_dollar")
    assert paths_of(result) == ["3-0-0", "0-0-4", "1-0-0", "0-0-0"]


def test_rank_upgrades_unknown_metric(ranked_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        rank_upgrades(ranked_database, metric="bogus")


def test_rank_upgrades_hard(ranked_database: sqlite3.Connection) -> None:
    result = rank_upgrades(ranked_database, difficulty="hard")
    assert paths_of(result) == ["0-0-0", "1-0-0", "3-0-0", "0-0-4"]
    assert value_of(result, "0-0-0", "total_cost") == 2700
    assert value_of(result, "0-0-0", "damage_per_dollar") == pytest.approx(0.00823045, rel=1e-6)


def test_rank_upgrades_unknown_difficulty(ranked_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        rank_upgrades(ranked_database, difficulty="nightmare")


def test_rank_upgrades_keeps_filters(ranked_database: sqlite3.Connection) -> None:
    result = rank_upgrades(ranked_database, UpgradeFilters(damage_type="Plasma"))
    assert paths_of(result) == ["3-0-0"]


def test_rank_upgrades_invalid_filter_still_raises(ranked_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        rank_upgrades(ranked_database, UpgradeFilters(min_range=-1))


def test_rank_upgrades_limit(ranked_database: sqlite3.Connection) -> None:
    assert paths_of(rank_upgrades(ranked_database, limit=2)) == ["0-0-0", "1-0-0"]


def test_rank_upgrades_limit_applies_after_ranking(ranked_database: sqlite3.Connection) -> None:
    assert paths_of(rank_upgrades(ranked_database, metric="dps", limit=1)) == ["3-0-0"]


def test_rank_upgrades_null_metric_last() -> None:
    connection = build_database({**UPGRADE_STATS, "0-1-0": NULL_RATE_STATS})
    by_dps = rank_upgrades(connection, metric="dps")
    by_dollar = rank_upgrades(connection)
    connection.close()
    assert paths_of(by_dps) == ["3-0-0", "0-0-4", "0-0-0", "1-0-0", "0-1-0"]
    assert pandas.isna(value_of(by_dps, "0-1-0", "dps"))
    assert paths_of(by_dollar) == ["0-0-0", "1-0-0", "3-0-0", "0-0-4", "0-1-0"]


def test_rank_upgrades_costs_not_loaded() -> None:
    connection = build_database(UPGRADE_STATS, with_costs=False)
    result = rank_upgrades(connection)
    connection.close()
    assert paths_of(result) == ["0-0-0", "0-0-4", "1-0-0", "3-0-0"]
    assert result["total_cost"].isna().all()
    assert result["damage_per_dollar"].isna().all()


@pytest.mark.parametrize("limit", [0, -1])
def test_rank_upgrades_limit_below_one_raises(
    ranked_database: sqlite3.Connection, limit: int | None
) -> None:
    with pytest.raises(QueryError, match=rf"limit must be at least 1, got {limit}"):
        rank_upgrades(ranked_database, limit=limit)


def test_rank_upgrades_limit_one_returns_one_row(ranked_database: sqlite3.Connection) -> None:
    assert len(rank_upgrades(ranked_database, limit=1)) == 1


def test_rank_upgrades_unknown_metric_message(ranked_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError, match=r'Cannot rank by "bogus"') as error:
        rank_upgrades(ranked_database, metric="bogus")
    for metric in METRICS:
        assert metric in str(error.value)


def test_rank_upgrades_unknown_difficulty_message(ranked_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError, match=r"Unknown difficulty: 'nightmare'"):
        rank_upgrades(ranked_database, difficulty="nightmare")


@pytest.mark.parametrize("limit", [None, 1, 2, 10])
def test_rank_upgrades_index_is_clean_range(
    ranked_database: sqlite3.Connection, limit: int | None
) -> None:
    result = rank_upgrades(ranked_database, metric="dps", limit=limit)
    assert isinstance(result.index, pandas.RangeIndex)
    assert list(result.index) == list(range(len(result)))
    assert "index" not in result.columns


EMPTY_RESULT_COLUMNS = {
    "total_cost",
    "dps",
    "moab_dps",
    "pierce_weighted_dps",
    "damage_per_dollar",
    "pierce_damage_per_dollar",
    "tower_name",
    "path",
}


@pytest.mark.parametrize("limit", [None, 1])
def test_rank_upgrades_empty_result_keeps_columns(
    ranked_database: sqlite3.Connection, limit: int | None
) -> None:
    result = rank_upgrades(ranked_database, UpgradeFilters(min_damage=1000), limit=limit)
    assert len(result) == 0
    assert EMPTY_RESULT_COLUMNS <= set(result.columns)


OPTIONAL_NUMBER = st.one_of(st.none(), st.integers(min_value=0, max_value=10).map(float))
VALID_PATHS = [
    "0-0-0",
    "1-0-0",
    "2-0-0",
    "3-0-0",
    "4-0-0",
    "0-2-0",
    "0-4-0",
    "0-0-3",
    "0-0-4",
    "2-2-0",
    "1-0-5",
    "0-3-2",
]
FILTER_STRATEGY = st.one_of(
    st.none(),
    st.builds(
        UpgradeFilters,
        min_damage=st.one_of(st.none(), st.integers(0, 3)),
        damage_type=st.one_of(st.none(), st.sampled_from(DAMAGE_TYPES)),
        can_hit_camo=st.one_of(st.none(), st.booleans()),
    ),
)


@st.composite
def random_rows(draw: st.DrawFn) -> list[dict[str, Any]]:
    paths = draw(st.lists(st.sampled_from(VALID_PATHS), min_size=1, max_size=8, unique=True))
    return [
        UpgradeRowFactory.build(
            path=path,
            damage_type=draw(st.sampled_from(DAMAGE_TYPES)),
            projectile_damage=draw(OPTIONAL_NUMBER),
            projectile_count=draw(OPTIONAL_NUMBER),
            attack_rate=draw(OPTIONAL_NUMBER),
            projectile_pierce=draw(OPTIONAL_NUMBER),
            can_hit_camo=draw(st.booleans()),
        )
        for path in paths
    ]


@settings(max_examples=60, deadline=None)
@given(
    rows=random_rows(),
    filters=FILTER_STRATEGY,
    metric=st.sampled_from(METRICS),
    with_costs=st.booleans(),
)
def test_rank_upgrades_is_permutation(
    rows: list[dict[str, Any]], filters: UpgradeFilters | None, metric: str, with_costs: bool
) -> None:
    connection = connect(":memory:")
    initialize_database(connection)
    insert_upgrade_rows(connection, rows)
    if with_costs:
        load_costs(connection, "Super Monkey", super_monkey_costs())
    expected = sorted(row["path"] for row in search_upgrades(connection, filters))
    ranked = rank_upgrades(connection, filters, metric=metric)
    connection.close()
    assert sorted(paths_of(ranked)) == expected


@settings(max_examples=60, deadline=None)
@given(
    paths=st.lists(st.sampled_from(VALID_PATHS), min_size=2, max_size=2, unique=True),
    damage=st.integers(1, 5),
    rate=st.sampled_from([0.045, 0.5, 1.0, 2.0]),
)
def test_rank_upgrades_cost_never_helps(paths: list[str], damage: int, rate: float) -> None:
    shared = {
        "projectile_damage": damage,
        "projectile_count": 1,
        "attack_rate": rate,
        "projectile_pierce": 1,
        "damage_type": "Normal",
    }
    connection = build_database({path: shared for path in paths})
    ranked = rank_upgrades(connection, metric="damage_per_dollar")
    connection.close()
    costs = list(ranked["total_cost"])
    assert costs == sorted(costs)


def test_rank_upgrades_max_cost_keeps_affordable(ranked_database: sqlite3.Connection) -> None:
    result = rank_upgrades(ranked_database, max_cost=27000)
    assert paths_of(result) == ["0-0-0", "1-0-0", "3-0-0"]


def test_rank_upgrades_max_cost_applies_before_limit(ranked_database: sqlite3.Connection) -> None:
    result = rank_upgrades(ranked_database, metric="dps", max_cost=5000, limit=1)
    assert paths_of(result) == ["0-0-0"]


def test_rank_upgrades_max_cost_none_affordable(ranked_database: sqlite3.Connection) -> None:
    assert rank_upgrades(ranked_database, max_cost=0).empty


def test_rank_upgrades_max_cost_drops_unknown_cost() -> None:
    connection = build_database(UPGRADE_STATS, with_costs=False)
    result = rank_upgrades(connection, max_cost=1_000_000)
    connection.close()
    assert result.empty


def test_rank_upgrades_negative_max_cost_raises(ranked_database: sqlite3.Connection) -> None:
    with pytest.raises(QueryError, match=r"max_cost must be 0 or more, got -1"):
        rank_upgrades(ranked_database, max_cost=-1)


def test_rank_upgrades_max_cost_uses_difficulty_cost(ranked_database: sqlite3.Connection) -> None:
    assert rank_upgrades(ranked_database, difficulty="hard", max_cost=2500).empty
