from __future__ import annotations

import json
from pathlib import Path

import pytest

from btd6.etl.extract import extract_income_thresholds
from tests.factories import IncomeSetFactory

FIXTURE = Path(__file__).parent / "fixtures" / "default_income_set.json"


def test_extract_income_thresholds_base() -> None:
    rows = extract_income_thresholds(json.loads(FIXTURE.read_text()))
    assert len(rows) == 6
    assert rows[0] == {"max_round": 50, "multiplier": 1}
    assert rows[-1] == {"max_round": 140, "multiplier": 0.04}
    assert all(list(row) == ["max_round", "multiplier"] for row in rows)


def test_extract_income_thresholds_matches_factory() -> None:
    assert extract_income_thresholds(IncomeSetFactory()) == extract_income_thresholds(
        json.loads(FIXTURE.read_text())
    )


def test_extract_income_thresholds_single() -> None:
    income_set = IncomeSetFactory(items=[{"threshold": 50, "multiplier": 1}])
    assert extract_income_thresholds(income_set) == [{"max_round": 50, "multiplier": 1}]


def test_extract_income_thresholds_empty() -> None:
    assert extract_income_thresholds(IncomeSetFactory(items=[])) == []


def test_extract_income_thresholds_keeps_order() -> None:
    items = [{"threshold": 9, "multiplier": 0.5}, {"threshold": 3, "multiplier": 1}]
    rows = extract_income_thresholds(IncomeSetFactory(items=items))
    assert [row["max_round"] for row in rows] == [9, 3]


def test_extract_income_thresholds_types() -> None:
    row = extract_income_thresholds(IncomeSetFactory(items=[{"threshold": "50", "multiplier": 1}]))[
        0
    ]
    assert type(row["max_round"]) is int
    assert type(row["multiplier"]) is float


@pytest.mark.parametrize(
    "income_set",
    [{}, {"thresholds": {}}, {"thresholds": []}, {"finalMultiplier": 0.02}],
)
def test_extract_income_thresholds_missing_key(income_set) -> None:
    with pytest.raises(ValueError, match="thresholds.items"):
        extract_income_thresholds(income_set)
