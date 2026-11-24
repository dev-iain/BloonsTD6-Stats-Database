from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6.formatting import income_summary
from btd6.income import RoundIncome


@pytest.mark.parametrize(
    ("round_number", "income", "expected"),
    [
        (1, RoundIncome(20.0, 101, 121.0), "Round 1: $20 pop cash + $101 end bonus = $121"),
        (40, RoundIncome(381.0, 140, 521.0), "Round 40: $381 pop cash + $140 end bonus = $521"),
        (
            63,
            RoundIncome(2663.0, 163, 2826.0),
            "Round 63: $2,663 pop cash + $163 end bonus = $2,826",
        ),
        (
            80,
            RoundIncome(1220.2, 180, 1400.2),
            "Round 80: $1,220.2 pop cash + $180 end bonus = $1,400.2",
        ),
        (
            100,
            RoundIncome(1334.6, 200, 1534.6),
            "Round 100: $1,334.6 pop cash + $200 end bonus = $1,534.6",
        ),
        (120, RoundIncome(0.0, 101, 101.0), "Round 120: $0 pop cash + $101 end bonus = $101"),
        (
            7,
            RoundIncome(0.1 + 0.2, 107, 0.1 + 0.2 + 107),
            "Round 7: $0.3 pop cash + $107 end bonus = $107.3",
        ),
        (9, RoundIncome(1000.0, 109, 1109.0), "Round 9: $1,000 pop cash + $109 end bonus = $1,109"),
        (2, RoundIncome(20, 102, 122), "Round 2: $20 pop cash + $102 end bonus = $122"),
    ],
)
def test_income_summary(round_number: int, income: RoundIncome, expected: str) -> None:
    assert income_summary(income, round_number) == expected


@given(
    round_number=st.integers(min_value=1, max_value=500),
    pop_cash=st.integers(min_value=0, max_value=10_000_000).map(lambda tenths: tenths / 10),
)
def test_income_summary_properties(round_number: int, pop_cash: float) -> None:
    income = RoundIncome(pop_cash, 100 + round_number, pop_cash + 100 + round_number)
    summary = income_summary(income, round_number)

    assert summary.startswith(f"Round {round_number}: $")
    assert "\n" not in summary
    assert ".0 " not in summary
    assert not summary.endswith(".0")
    total_text = summary.rsplit("= $", 1)[1].replace(",", "")
    assert float(total_text) == pytest.approx(income.total, abs=0.05)
