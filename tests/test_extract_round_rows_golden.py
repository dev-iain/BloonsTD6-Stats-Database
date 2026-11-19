from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from btd6.etl.extract import extract_round_rows

FIXTURE_DIR = Path(__file__).parent / "fixtures"
ROUNDSET_PATH = FIXTURE_DIR / "default_roundset_first10.json"
GOLDEN_CSV_PATH = FIXTURE_DIR / "default_roundset_first10_rows.csv"


@pytest.fixture(scope="module")
def roundset() -> dict[str, Any]:
    with open(ROUNDSET_PATH) as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def built_frame(roundset: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(extract_round_rows(roundset))


def test_matches_golden_csv(built_frame: pd.DataFrame) -> None:
    golden_frame = pd.read_csv(GOLDEN_CSV_PATH)
    pd.testing.assert_frame_equal(built_frame, golden_frame, check_dtype=False)


def test_row_count_equals_group_count(built_frame: pd.DataFrame, roundset: dict[str, Any]) -> None:
    group_total = sum(len(entry["bloonGroups"]) for entry in roundset["rounds"])
    assert len(built_frame) == group_total


def test_round_three_keeps_repeated_red(built_frame: pd.DataFrame) -> None:
    round_three = built_frame[built_frame["round"] == 3]
    assert list(round_three["bloon"]) == ["Red", "Blue", "Red"]
    assert list(round_three["count"]) == [10, 5, 15]
    assert list(round_three["group_index"]) == [0, 1, 2]
