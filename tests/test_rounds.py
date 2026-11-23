from __future__ import annotations

import dataclasses
import sqlite3

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.db import apply_migrations, connect
from btd6.rounds import RoundSummary, get_round, get_round_summary
from tests.rounds_fixture import LOADED_ROUNDS, build_rounds_db


@pytest.fixture(scope="module")
def rounds_db() -> sqlite3.Connection:
    return build_rounds_db()


def test_get_round_first_round(rounds_db: sqlite3.Connection) -> None:
    groups = get_round(rounds_db, 1)

    assert len(groups) == 1
    group = groups[0]
    assert (group.group_index, group.bloon, group.count, group.rbe) == (0, "Red", 20, 1)
    assert not (group.is_camo or group.is_regrow or group.is_fortified or group.is_moab)


def test_get_round_last_loaded_round(rounds_db: sqlite3.Connection) -> None:
    groups = get_round(rounds_db, 40)

    assert [(group.bloon, group.count) for group in groups] == [("Pink", 20), ("Moab", 1)]
    assert groups[1].is_moab is True
    assert groups[1].rbe == 616


def test_get_round_zero(rounds_db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="Round 0 "):
        get_round(rounds_db, 0)


def test_get_round_negative(rounds_db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="Round -1 "):
        get_round(rounds_db, -1)


def test_get_round_beyond_loaded_data(rounds_db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError) as excinfo:
        get_round(rounds_db, 41)

    assert str(excinfo.value) == "Round 41 is not loaded; loaded rounds are 1-40"


def test_get_round_past_max_round(rounds_db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="Round 101 "):
        get_round(rounds_db, 101)


@pytest.mark.parametrize("value", ["1", 1.0, True, None])
def test_get_round_wrong_type(rounds_db: sqlite3.Connection, value: object) -> None:
    with pytest.raises(TypeError):
        get_round(rounds_db, value)  # type: ignore[arg-type]


def test_get_round_string_argument(rounds_db: sqlite3.Connection) -> None:
    with pytest.raises(TypeError):
        get_round(rounds_db, "1")  # type: ignore[arg-type]


def test_get_round_float_argument(rounds_db: sqlite3.Connection) -> None:
    with pytest.raises(TypeError):
        get_round(rounds_db, 1.0)  # type: ignore[arg-type]


def test_get_round_bool_argument(rounds_db: sqlite3.Connection) -> None:
    with pytest.raises(TypeError):
        get_round(rounds_db, True)


def test_get_round_none_argument(rounds_db: sqlite3.Connection) -> None:
    with pytest.raises(TypeError):
        get_round(rounds_db, None)  # type: ignore[arg-type]


def test_get_round_no_data_loaded() -> None:
    connection = connect(":memory:")
    apply_migrations(connection)

    with pytest.raises(ValueError) as excinfo:
        get_round(connection, 1)

    assert str(excinfo.value) == "No round data loaded"


def test_get_round_repeated_bloon_keeps_order(rounds_db: sqlite3.Connection) -> None:
    groups = get_round(rounds_db, 3)

    assert [(g.group_index, g.bloon, g.count) for g in groups] == [
        (0, "Red", 5),
        (1, "Blue", 3),
        (2, "Red", 2),
    ]


def test_get_round_modifier_flags(rounds_db: sqlite3.Connection) -> None:
    groups = get_round(rounds_db, 24)

    assert len(groups) == 1
    assert groups[0].bloon == "Blue"
    assert groups[0].is_camo is True
    assert groups[0].is_regrow is False


def test_round_group_is_frozen(rounds_db: sqlite3.Connection) -> None:
    group = get_round(rounds_db, 1)[0]

    with pytest.raises(dataclasses.FrozenInstanceError):
        group.count = 5  # type: ignore[misc]


@settings(max_examples=40, deadline=None)
@given(st.integers(min_value=1, max_value=LOADED_ROUNDS))
def test_get_round_sorted_for_every_round(number: int) -> None:
    groups = get_round(ROUNDS_DB, number)

    indexes = [group.group_index for group in groups]
    assert groups
    assert indexes == sorted(indexes)


def test_get_round_summary_first_round(rounds_db: sqlite3.Connection) -> None:
    assert get_round_summary(rounds_db, 1) == RoundSummary(1, 20, 20, False, False, False, False)


def test_get_round_summary_moab_round(rounds_db: sqlite3.Connection) -> None:
    summary = get_round_summary(rounds_db, 40)

    assert (summary.total_bloons, summary.total_rbe) == (21, 716)
    assert summary.has_moab is True
    assert not (summary.has_camo or summary.has_lead or summary.has_ceramic)


def test_get_round_summary_camo_round(rounds_db: sqlite3.Connection) -> None:
    summary = get_round_summary(rounds_db, 24)

    assert (summary.total_bloons, summary.total_rbe) == (10, 20)
    assert summary.has_camo is True
    assert summary.has_moab is False


def test_get_round_summary_lead_round(rounds_db: sqlite3.Connection) -> None:
    summary = get_round_summary(rounds_db, 27)

    assert (summary.total_bloons, summary.total_rbe) == (6, 138)
    assert summary.has_lead is True
    assert summary.has_ceramic is False


def test_get_round_summary_ceramic_round(rounds_db: sqlite3.Connection) -> None:
    summary = get_round_summary(rounds_db, 35)

    assert (summary.total_bloons, summary.total_rbe) == (3, 312)
    assert summary.has_ceramic is True
    assert summary.has_lead is False


def test_get_round_summary_repeated_bloon_round(rounds_db: sqlite3.Connection) -> None:
    assert get_round_summary(rounds_db, 3) == RoundSummary(3, 10, 13, False, False, False, False)


def test_get_round_summary_zero(rounds_db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="Round 0 "):
        get_round_summary(rounds_db, 0)


def test_get_round_summary_beyond_loaded_data(rounds_db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError) as excinfo:
        get_round_summary(rounds_db, 41)

    assert str(excinfo.value) == "Round 41 is not loaded; loaded rounds are 1-40"


def test_get_round_summary_bool_argument(rounds_db: sqlite3.Connection) -> None:
    with pytest.raises(TypeError):
        get_round_summary(rounds_db, True)


def test_get_round_summary_lead_and_ceramic() -> None:
    connection = build_rounds_db({2: [("Lead", 1, False), ("Ceramic", 1, False)]})

    summary = get_round_summary(connection, 2)

    assert summary.has_lead is True
    assert summary.has_ceramic is True


def test_get_round_summary_camo_lead_sets_both_flags() -> None:
    connection = build_rounds_db({2: [("Lead", 1, True)]})

    summary = get_round_summary(connection, 2)

    assert summary.has_lead is True
    assert summary.has_camo is True


@settings(max_examples=40, deadline=None)
@given(st.integers(min_value=1, max_value=LOADED_ROUNDS))
def test_get_round_summary_matches_get_round(number: int) -> None:
    groups = get_round(ROUNDS_DB, number)
    summary = get_round_summary(ROUNDS_DB, number)

    assert summary.total_bloons == sum(group.count for group in groups)
    assert summary.total_rbe == sum(group.count * group.rbe for group in groups)


ROUNDS_DB = build_rounds_db()
