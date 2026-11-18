from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from btd6.etl.extract import build_dataframe

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "super_monkey_resolved.json"
GOLDEN_CSV_PATH = Path(__file__).resolve().parent.parent / "data.csv"


def load_resolved() -> dict[str, dict[str, Any]]:
    with open(FIXTURE_PATH) as handle:
        return json.load(handle)


def roundtrip(dataframe: pd.DataFrame) -> pd.DataFrame:
    buffer = io.StringIO()
    dataframe.to_csv(buffer)
    buffer.seek(0)
    return pd.read_csv(buffer, index_col="path")


@pytest.fixture(scope="module")
def built_frame() -> pd.DataFrame:
    return build_dataframe(load_resolved())


@pytest.fixture(scope="module")
def golden_frame() -> pd.DataFrame:
    return pd.read_csv(GOLDEN_CSV_PATH, index_col="path")


def test_matches_golden_csv(built_frame: pd.DataFrame, golden_frame: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(roundtrip(built_frame), golden_frame, check_dtype=False)


def test_detects_changed_fixture_value(golden_frame: pd.DataFrame) -> None:
    resolved = load_resolved()
    resolved["_000"]["range"] += 1
    with pytest.raises(AssertionError):
        pd.testing.assert_frame_equal(
            roundtrip(build_dataframe(resolved)), golden_frame, check_dtype=False
        )


def test_row_count(built_frame: pd.DataFrame) -> None:
    assert len(built_frame) == 64


@pytest.mark.parametrize(
    ("column", "expected_missing"),
    [("footprint_radius", 10), ("ability_cooldown", 39)],
)
def test_missing_value_counts(
    built_frame: pd.DataFrame, column: str, expected_missing: int
) -> None:
    assert built_frame[column].isna().sum() == expected_missing


@pytest.mark.parametrize(
    ("path", "damage_type", "pierce"),
    [("0-0-0", "Sharp", 1), ("1-0-0", "Energy", 2)],
)
def test_spot_checks(built_frame: pd.DataFrame, path: str, damage_type: str, pierce: int) -> None:
    row = built_frame.loc[path]
    assert row["damage_type"] == damage_type
    assert row["projectile_pierce"] == pierce
