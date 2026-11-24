from __future__ import annotations

import json
from pathlib import Path

import pytest

from btd6.etl.extract import extract_bloon_rows, parse_bloon_children
from tests.factories import RawBloonFactory

FIXTURE = Path(__file__).parent / "fixtures" / "bloons_cargo_response.json"
TIMES = "×"


def link(page: str, label: str) -> str:
    return f"[[{page} (BTD6)|{label}]]"


@pytest.mark.parametrize(
    ("parent_of", "expected"),
    [
        ("", []),
        (f"{link('Ceramic Bloon', 'Ceramic Bloon')} {TIMES}4", [("Ceramic", 4)]),
        (f"{link('Red Bloon', 'Red Bloon')} {TIMES}1", [("Red", 1)]),
        (
            f"{link('Black Bloon', 'Black Bloon')} {TIMES}1, "
            f"{link('White Bloon', 'White Bloon')} {TIMES}1",
            [("Black", 1), ("White", 1)],
        ),
        (
            f"{link('Camo Bloon', 'Camo')} {link('Regrow Bloon', 'Regrow')} "
            f"{link('Ceramic', 'Ceramic')} {TIMES}4",
            [("Ceramic", 4)],
        ),
        (f"{link('MOAB', 'MOAB')} {TIMES}4", [("Moab", 4)]),
        (f"{link('BFB', 'BFB')} {TIMES}22", [("Bfb", 22)]),
        (
            f"{link('ZOMG', 'ZOMG')} {TIMES}2, {link('DDT', 'DDT')} {TIMES}3",
            [("Zomg", 2), ("Ddt", 3)],
        ),
    ],
)
def test_parse_bloon_children(parent_of, expected) -> None:
    assert parse_bloon_children(parent_of) == expected


def test_parse_bloon_children_regrow_zebra_names_only_zebra() -> None:
    text = (
        f"{link('Zebra Bloon', 'Zebra Bloon')} {TIMES}1, "
        f"{link('Regrow Bloon', 'Regrow')} Zebra Bloon {TIMES}1"
    )
    assert {name for name, _ in parse_bloon_children(text)} == {"Zebra"}


def children_text(*pairs: tuple[str, str, int]) -> str:
    return ", ".join(f"{link(page, label)} {TIMES}{count}" for page, label, count in pairs)


RAW_CHAIN = [
    ("Red", "", False),
    ("Blue", children_text(("Red Bloon", "Red Bloon", 1)), False),
    ("Green", children_text(("Blue Bloon", "Blue Bloon", 1)), False),
    ("Yellow", children_text(("Green Bloon", "Green Bloon", 1)), False),
    ("Pink", children_text(("Yellow Bloon", "Yellow Bloon", 1)), False),
    ("Black", children_text(("Pink Bloon", "Pink Bloon", 2)), False),
    ("White", children_text(("Pink Bloon", "Pink Bloon", 2)), False),
    ("Lead", children_text(("Black Bloon", "Black Bloon", 2)), False),
    (
        "Zebra",
        children_text(("Black Bloon", "Black Bloon", 1), ("White Bloon", "White Bloon", 1)),
        False,
    ),
    ("Rainbow", children_text(("Zebra Bloon", "Zebra Bloon", 2)), False),
    ("Ceramic", children_text(("Rainbow Bloon", "Rainbow Bloon", 2)), False),
    ("Moab", children_text(("Ceramic Bloon", "Ceramic Bloon", 4)), True),
    ("Bfb", children_text(("MOAB", "MOAB", 4)), True),
    ("Zomg", children_text(("BFB", "BFB", 4)), True),
    ("Ddt", children_text(("Ceramic Bloon", "Ceramic Bloon", 4)), True),
    ("Bad", children_text(("ZOMG", "ZOMG", 2), ("DDT", "DDT", 3)), True),
]
EXPECTED = {
    "Red": (1, 1),
    "Lead": (23, 7),
    "Zebra": (23, 7),
    "Rainbow": (47, 8),
    "Ceramic": (95, 95),
    "Moab": (381, 381),
    "Ddt": (381, 381),
    "Bfb": (1525, 1525),
    "Zomg": (6101, 6101),
    "Bad": (13346, 13346),
}


def chain_rows() -> list[dict]:
    raw = [
        RawBloonFactory(bloon_id=name, parent_of=text, is_moab="1" if moab else "")
        for name, text, moab in RAW_CHAIN
    ]
    return extract_bloon_rows(raw)


@pytest.mark.parametrize(("name", "expected"), EXPECTED.items())
def test_extract_bloon_rows_pop_cash(name, expected) -> None:
    row = next(row for row in chain_rows() if row["name"] == name)
    assert (row["pop_cash"], row["pop_cash_super"]) == expected


def test_extract_bloon_rows_pop_cash_keys_last() -> None:
    assert list(chain_rows()[0])[-2:] == ["pop_cash", "pop_cash_super"]


def test_extract_bloon_rows_pop_cash_from_cargo_fixture() -> None:
    titles = [entry["title"] for entry in json.loads(FIXTURE.read_text())["cargoquery"]]
    raw = [{key.replace(" ", "_"): value for key, value in title.items()} for title in titles]
    rows = {row["name"]: row for row in extract_bloon_rows(raw)}
    assert rows["Red"]["pop_cash"] == 1
    assert rows["Blue"]["pop_cash"] == 2
    assert rows["Green"]["pop_cash"] == 3
    assert rows["Blue"]["pop_cash_super"] == 2


def test_extract_bloon_rows_unknown_child_is_leaf() -> None:
    raw = [RawBloonFactory(bloon_id="Blue", parent_of=children_text(("Red Bloon", "Red Bloon", 1)))]
    assert extract_bloon_rows(raw)[0]["pop_cash"] == 2
