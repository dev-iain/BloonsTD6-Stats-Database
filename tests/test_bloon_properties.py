from __future__ import annotations

import json
from pathlib import Path

import pytest

from btd6.etl.extract import (
    BLOON_FLAG_COLUMNS,
    extract_bloon_row,
    immune_damage_types,
    parse_bloon_properties,
)
from btd6.etl.fetch import normalize_cargo_keys

FIXTURE = Path(__file__).parent / "fixtures" / "bloons_immunity_cargo_response.json"
FLAGS = BLOON_FLAG_COLUMNS
LEAD_TEXT = "[[damage type|Sharp, Shatter, Cold, Energy]]"
ZEBRA_TEXT = "[[damage type|Explosion, Cold, Glacier, Frigid]]"
DDT_TEXT = "[[damage type|Sharp, Shatter, Cold, Energy, Explosion]]"


def flags(**set_flags: int) -> dict[str, int]:
    return {flag: set_flags.get(flag, 0) for flag in FLAGS}


@pytest.fixture(scope="module")
def fixture_rows() -> dict[str, dict[str, str]]:
    titles = [entry["title"] for entry in json.loads(FIXTURE.read_text())["cargoquery"]]
    return {title["id"]: normalize_cargo_keys(title) for title in titles}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (LEAD_TEXT, flags(has_lead=1)),
        ("", flags()),
        ("[[Slow]], [[blowback]], [[knockback]]", flags()),
        (ZEBRA_TEXT, flags(has_black=1, has_white=1)),
        ("[[damage type|Sharp]]", flags()),
        ("Energy, Plasma, Acid", flags(has_glass=1)),
        (None, flags()),
        ("Sharp, Shatter, Cold, Energy", flags(has_lead=1)),
        (DDT_TEXT, flags(has_lead=1, has_black=1)),
        ("[[damage type|energy, PLASMA, fire, frigid]]", flags(has_purple=1)),
    ],
    ids=[
        "lead",
        "empty",
        "status_effects",
        "zebra",
        "partial",
        "glass",
        "none",
        "plain_text",
        "ddt_never_frozen",
        "case_insensitive",
    ],
)
def test_parse_bloon_properties(text: str | None, expected: dict[str, int]) -> None:
    assert parse_bloon_properties(text) == expected


def test_extract_bloon_row_lead_flag() -> None:
    row = extract_bloon_row({"id": "Lead", "immunity": LEAD_TEXT})
    assert {flag: row[flag] for flag in FLAGS} == flags(has_lead=1)


def test_extract_bloon_row_missing_immunity() -> None:
    row = extract_bloon_row({"id": "Red"})
    assert {flag: row[flag] for flag in FLAGS} == flags()


def test_extract_bloon_row_moab_flags_independent() -> None:
    row = extract_bloon_row({"id": "Ddt", "is_moab": "1", "immunity": LEAD_TEXT})
    assert row["is_moab"] is True
    assert row["has_lead"] == 1


def test_extract_bloon_row_flags_follow_speed() -> None:
    row = extract_bloon_row({"id": "Red"})
    assert list(row)[-6:] == list(FLAGS)


EXPECTED_FIXTURE_FLAGS = {
    "Red": flags(),
    "Blue": flags(),
    "Green": flags(),
    "Yellow": flags(),
    "Pink": flags(),
    "Black": flags(has_black=1),
    "White": flags(has_white=1),
    "Purple": flags(has_purple=1),
    "Lead": flags(has_lead=1),
    "Zebra": flags(has_black=1, has_white=1),
    "Rainbow": flags(),
    "Ceramic": flags(),
    "Moab": flags(),
    "Bfb": flags(),
    "Zomg": flags(),
    "Ddt": flags(has_lead=1, has_black=1),
    "Bad": flags(),
}


def test_extract_bloon_row_fixture_flags(fixture_rows) -> None:
    for name, expected in EXPECTED_FIXTURE_FLAGS.items():
        row = extract_bloon_row(fixture_rows[name])
        assert {flag: row[flag] for flag in FLAGS} == expected, name


@pytest.mark.parametrize("text", [None, ""])
def test_immune_damage_types_empty(text: str | None) -> None:
    assert immune_damage_types(text) == set()
