from __future__ import annotations

import copy
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6.etl.extract import extract_bloon_rows

RED = {
    "id": "Red",
    "name": "Red Bloon",
    "health": "1",
    "health_fort": "2",
    "layers": "1",
    "rbe": "1",
    "rbe_fort": "2",
    "is_moab": "0",
    "speed": "1.0",
    "immunity": "",
    "parent_of": "",
    "child_of": "",
}
MOAB = RED | {
    "id": "Moab",
    "name": "MOAB",
    "health": "200",
    "rbe": "616",
    "is_moab": "1",
    "speed": "1.0",
}
OUTPUT_KEYS = [
    "name",
    "health",
    "health_fort",
    "layers",
    "rbe",
    "rbe_fort",
    "is_moab",
    "speed",
    "pop_cash",
    "pop_cash_super",
]


def red_with(**changes: str) -> dict[str, str]:
    return RED | changes


def test_extract_bloon_rows_base() -> None:
    rows = extract_bloon_rows([RED, MOAB])

    assert len(rows) == 2
    assert rows[0] == {
        "name": "Red",
        "health": 1,
        "health_fort": 2,
        "layers": 1,
        "rbe": 1,
        "rbe_fort": 2,
        "is_moab": False,
        "speed": 1.0,
        "pop_cash": 1,
        "pop_cash_super": 1,
    }
    assert list(rows[0]) == OUTPUT_KEYS
    assert type(rows[0]["health"]) is int
    assert type(rows[0]["speed"]) is float
    assert type(rows[0]["is_moab"]) is bool


def test_extract_bloon_rows_empty() -> None:
    assert extract_bloon_rows([]) == []


def test_extract_bloon_rows_single() -> None:
    rows = extract_bloon_rows([RED])

    assert len(rows) == 1
    assert rows[0]["name"] == "Red"


def test_extract_bloon_rows_empty_health_is_none() -> None:
    row = extract_bloon_rows([red_with(health="")])[0]

    assert row["health"] is None
    assert row["health_fort"] == 2
    assert row["speed"] == 1.0


def test_extract_bloon_rows_missing_health_is_none() -> None:
    raw = dict(RED)
    del raw["health"]

    assert extract_bloon_rows([raw])[0]["health"] is None


def test_extract_bloon_rows_non_numeric_health() -> None:
    with pytest.raises(ValueError, match=r"(?s)Red.*health|health.*Red"):
        extract_bloon_rows([red_with(health="abc")])


def test_extract_bloon_rows_speed_whole_number_is_float() -> None:
    speed = extract_bloon_rows([red_with(speed="2")])[0]["speed"]

    assert speed == 2.0
    assert type(speed) is float


def test_extract_bloon_rows_empty_speed_is_none() -> None:
    assert extract_bloon_rows([red_with(speed="")])[0]["speed"] is None


def test_extract_bloon_rows_is_moab_true() -> None:
    assert extract_bloon_rows([RED, MOAB])[1]["is_moab"] is True


def test_extract_bloon_rows_empty_is_moab_is_false() -> None:
    assert extract_bloon_rows([red_with(is_moab="")])[0]["is_moab"] is False


def test_extract_bloon_rows_missing_is_moab_is_false() -> None:
    raw = dict(RED)
    del raw["is_moab"]

    assert extract_bloon_rows([raw])[0]["is_moab"] is False


def test_extract_bloon_rows_invalid_is_moab() -> None:
    with pytest.raises(ValueError, match=r'is_moab.*"2"|"2".*is_moab'):
        extract_bloon_rows([red_with(is_moab="2")])


def test_extract_bloon_rows_odd_names_kept() -> None:
    rows = extract_bloon_rows([red_with(id="Ddt"), red_with(id="Zomg")])

    assert [row["name"] for row in rows] == ["Ddt", "Zomg"]


def test_extract_bloon_rows_name_stripped() -> None:
    assert extract_bloon_rows([red_with(id=" Red ")])[0]["name"] == "Red"


def test_extract_bloon_rows_modifier_name_not_split() -> None:
    row = extract_bloon_rows([red_with(id="RedCamo")])[0]

    assert row["name"] == "RedCamo"
    assert list(row) == OUTPUT_KEYS


def test_extract_bloon_rows_empty_name() -> None:
    with pytest.raises(ValueError, match="name"):
        extract_bloon_rows([red_with(id="")])


@pytest.mark.parametrize("field", ["health_fort", "layers", "rbe", "rbe_fort"])
def test_extract_bloon_rows_integer_fields(field: str) -> None:
    converted = extract_bloon_rows([red_with(**{field: "7"})])[0][field]
    blank = extract_bloon_rows([red_with(**{field: ""})])[0][field]

    assert converted == 7
    assert type(converted) is int
    assert blank is None


def test_extract_bloon_rows_name_is_cargo_id() -> None:
    row = extract_bloon_rows([RED])[0]

    assert row["name"] == "Red"
    assert "Bloon" not in row["name"]


def test_extract_bloon_rows_drops_unstored_fields() -> None:
    row = extract_bloon_rows([RED])[0]

    for field in ("id", "immunity", "parent_of", "child_of"):
        assert field not in row


def test_extract_bloon_rows_does_not_mutate_input() -> None:
    raw: list[dict[str, Any]] = [dict(RED), dict(MOAB)]
    before = copy.deepcopy(raw)

    extract_bloon_rows(raw)

    assert raw == before


@given(number=st.integers(min_value=0, max_value=10**6))
def test_extract_bloon_rows_health_property(number: int) -> None:
    assert extract_bloon_rows([red_with(health=str(number))])[0]["health"] == number
