from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from btd6.etl.extract import extract_row

FIXTURE_DIR = Path(__file__).parent / "fixtures"

EXPECTED_ROWS: dict[str, list[tuple[str, str, int, int, int]]] = {
    "dart_monkey_resolved_sample.json": [
        ("0-0-0", "Sharp", 1, 2, 300),
        ("1-0-0", "Sharp", 1, 3, 300),
        ("0-0-5", "Normal", 8, 8, 600),
    ],
    "boomerang_monkey_resolved_sample.json": [
        ("0-0-0", "Sharp", 1, 4, 175),
        ("1-0-0", "Sharp", 1, 8, 175),
        ("0-0-3", "Normal", 2, 18, 175),
    ],
    "bomb_shooter_resolved_sample.json": [
        ("0-0-0", "Normal", None, 1, 180),
        ("2-0-0", "Normal", None, 1, 180),
        ("2-0-3", "Explosion", 2, 38, None),
    ],
    "sniper_monkey_resolved_sample.json": [
        ("0-0-0", "Sharp", 2, 1, None),
        ("1-0-0", "Normal", 4, 1, None),
        ("0-5-0", "Normal", 2, 5, None),
    ],
    "ice_monkey_resolved_sample.json": [
        ("0-0-0", "Cold", 1, 40, None),
        ("0-0-3", "Normal", None, 1, 300),
        ("2-0-0", "Glacier", 1, 40, None),
    ],
}


def load_sample(file_name: str) -> dict[str, dict[str, Any]]:
    with open(FIXTURE_DIR / file_name) as handle:
        return json.load(handle)


@pytest.mark.parametrize("file_name", EXPECTED_ROWS)
def test_extract_row_matches_documented_values(file_name: str) -> None:
    sample = load_sample(file_name)
    expected = EXPECTED_ROWS[file_name]
    rows = [extract_row(code, stats) for code, stats in sample.items()]
    actual = [
        (
            row["path"],
            row["damage_type"],
            row["projectile_damage"],
            row["projectile_pierce"],
            row["projectile_speed"],
        )
        for row in rows
    ]
    assert actual == expected


@pytest.mark.parametrize("file_name", EXPECTED_ROWS)
def test_projectile_count_is_null_in_every_sampled_row(file_name: str) -> None:
    sample = load_sample(file_name)
    assert all(
        extract_row(code, stats)["projectile_count"] is None for code, stats in sample.items()
    )
