from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6.etl.extract import extract_round_rows
from btd6.etl.fetch import MAX_ROUND

ROW_KEYS = {"round", "group_index", "bloon", "count", "start", "duration"}


def build_group(
    bloon: str, count: int = 20, start: float = 0, duration: float = 17.5125
) -> dict[str, Any]:
    return {"bloon": bloon, "count": count, "start": start, "duration": duration}


def build_round(*bloons: str) -> dict[str, Any]:
    return {"bloonGroups": [build_group(bloon) for bloon in bloons]}


def build_roundset(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    return {"rounds": rounds}


def base_roundset() -> dict[str, Any]:
    return build_roundset(
        [build_round("Red"), build_round("Red", "Blue"), build_round("Red", "Blue", "Red")]
    )


def long_roundset(total_rounds: int) -> dict[str, Any]:
    return build_roundset([build_round("Red", "Blue") for _ in range(total_rounds)])


def rows_for_round(rows: list[dict[str, Any]], number: int) -> list[dict[str, Any]]:
    return [row for row in rows if row["round"] == number]


def test_extract_round_rows_base() -> None:
    rows = extract_round_rows(base_roundset(), 100)
    assert [row["round"] for row in rows] == [1, 2, 2, 3, 3, 3]
    round_two = rows_for_round(rows, 2)
    assert [(row["group_index"], row["bloon"]) for row in round_two] == [(0, "Red"), (1, "Blue")]
    assert all(set(row) == ROW_KEYS for row in rows)


def test_extract_round_rows_exactly_max() -> None:
    rows = extract_round_rows(long_roundset(100), 100)
    assert len(rows) == 200
    assert rows[-1]["round"] == 100


def test_extract_round_rows_truncates_past_max() -> None:
    rows = extract_round_rows(long_roundset(101), 100)
    assert max(row["round"] for row in rows) == 100
    assert rows_for_round(rows, 101) == []


def test_extract_round_rows_no_rounds() -> None:
    assert extract_round_rows(build_roundset([]), 100) == []


def test_extract_round_rows_single_group() -> None:
    rows = rows_for_round(extract_round_rows(base_roundset(), 100), 1)
    assert len(rows) == 1
    assert rows[0]["group_index"] == 0
    assert rows[0]["duration"] == 17.5125
    assert rows[0]["count"] == 20
    assert rows[0]["start"] == 0


def test_extract_round_rows_repeated_bloon() -> None:
    rows = rows_for_round(extract_round_rows(base_roundset(), 100), 3)
    assert [row["group_index"] for row in rows] == [0, 1, 2]
    assert [row["bloon"] for row in rows] == ["Red", "Blue", "Red"]


def test_extract_round_rows_empty_round_keeps_numbering() -> None:
    roundset = build_roundset([build_round("Red"), build_round(), build_round("Blue")])
    rows = extract_round_rows(roundset, 100)
    assert [row["round"] for row in rows] == [1, 3]
    assert rows_for_round(rows, 2) == []


@pytest.mark.parametrize("bad_max", [0, -1])
def test_extract_round_rows_invalid_max_round(bad_max: int) -> None:
    message = f"max_round must be at least 1, got {bad_max}"
    with pytest.raises(ValueError) as caught:
        extract_round_rows(base_roundset(), bad_max)
    assert str(caught.value) == message


def test_extract_round_rows_missing_rounds_key() -> None:
    with pytest.raises(ValueError, match='roundset has no "rounds" list'):
        extract_round_rows({}, 100)


def test_extract_round_rows_default_max_round() -> None:
    roundset = long_roundset(MAX_ROUND + 5)
    assert extract_round_rows(roundset) == extract_round_rows(roundset, max_round=100)
    assert MAX_ROUND == 100


@given(max_round=st.integers(min_value=1, max_value=150))
def test_extract_round_rows_respects_max_and_order(max_round: int) -> None:
    rows = extract_round_rows(long_roundset(120), max_round)
    keys = [(row["round"], row["group_index"]) for row in rows]
    assert keys == sorted(keys)
    assert max(row["round"] for row in rows) <= max_round
