from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6.etl.extract import extract_bloon_rows, split_bloon_name

FIXTURES = Path(__file__).parent / "fixtures"


def fetch_title(entry: dict) -> dict:
    return {key.replace(" ", "_"): value for key, value in entry["title"].items()}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Red", ("Red", False, False, False)),
        ("CamoRed", ("CamoRed", False, False, False)),
        ("Camouflage", ("Camouflage", False, False, False)),
        ("redcamo", ("redcamo", False, False, False)),
    ],
)
def test_split_bloon_name_unmodified_names(name: str, expected: tuple) -> None:
    assert split_bloon_name(name) == expected


def test_split_bloon_name_plain() -> None:
    assert split_bloon_name("Red") == ("Red", False, False, False)


def test_split_bloon_name_camo() -> None:
    assert split_bloon_name("RedCamo") == ("Red", True, False, False)


def test_split_bloon_name_regrow() -> None:
    assert split_bloon_name("BlueRegrow") == ("Blue", False, True, False)


def test_split_bloon_name_fortified() -> None:
    assert split_bloon_name("MoabFortified") == ("Moab", False, False, True)


def test_split_bloon_name_regrow_camo() -> None:
    assert split_bloon_name("GreenRegrowCamo") == ("Green", True, True, False)


def test_split_bloon_name_camo_fortified() -> None:
    assert split_bloon_name("CeramicCamoFortified") == ("Ceramic", True, False, True)


def test_split_bloon_name_all_modifiers() -> None:
    assert split_bloon_name("CeramicRegrowCamoFortified") == ("Ceramic", True, True, True)


def test_split_bloon_name_empty() -> None:
    with pytest.raises(ValueError, match="empty bloon name"):
        split_bloon_name("")


def test_split_bloon_name_modifier_only() -> None:
    with pytest.raises(ValueError):
        split_bloon_name("Camo")


def test_split_bloon_name_modifier_prefix_kept() -> None:
    assert split_bloon_name("CamoRed") == ("CamoRed", False, False, False)


def test_split_bloon_name_longer_word_not_split() -> None:
    assert split_bloon_name("Camouflage") == ("Camouflage", False, False, False)


def test_split_bloon_name_case_sensitive() -> None:
    assert split_bloon_name("redcamo") == ("redcamo", False, False, False)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ddt", ("Ddt", False, False, False)),
        ("DdtCamo", ("Ddt", True, False, False)),
        ("ZomgFortified", ("Zomg", False, False, True)),
        ("Zomg", ("Zomg", False, False, False)),
        ("Bfb", ("Bfb", False, False, False)),
        ("Bad", ("Bad", False, False, False)),
        ("MoabFortified", ("Moab", False, False, True)),
    ],
)
def test_split_bloon_name_base_bloons(name: str, expected: tuple) -> None:
    assert split_bloon_name(name) == expected


def test_split_bloon_name_suffix_order_irrelevant() -> None:
    assert split_bloon_name("BlueCamoRegrow") == ("Blue", True, True, False)
    assert split_bloon_name("CeramicRegrowFortifiedCamo") == ("Ceramic", True, True, True)


def test_split_bloon_name_fixture_names_resolve() -> None:
    roundset = json.loads((FIXTURES / "default_roundset_first10.json").read_text(encoding="utf-8"))
    bloons = json.loads((FIXTURES / "bloons_cargo_response.json").read_text(encoding="utf-8"))
    known = {extract_bloon_rows([fetch_title(entry)])[0]["name"] for entry in bloons["cargoquery"]}
    names = {
        group["bloon"] for round_data in roundset["rounds"] for group in round_data["bloonGroups"]
    }

    assert names
    for name in names:
        assert split_bloon_name(name)[0] in known


@given(
    base=st.sampled_from(["Red", "Blue", "Moab", "Ddt"]),
    regrow=st.booleans(),
    camo=st.booleans(),
    fortified=st.booleans(),
)
def test_split_bloon_name_round_trip(base: str, regrow: bool, camo: bool, fortified: bool) -> None:
    name = base + ("Regrow" if regrow else "") + ("Camo" if camo else "")
    name += "Fortified" if fortified else ""

    assert split_bloon_name(name) == (base, camo, regrow, fortified)
