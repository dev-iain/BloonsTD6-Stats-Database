from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from btd6.db.connection import connect
from btd6.db.round_loader import BLOON_COLUMNS, bloon_params, load_bloons, load_rounds
from btd6.db.seed import initialize_database
from btd6.etl import fetch
from btd6.etl.extract import (
    build_group_rows,
    extract_bloon_row,
    extract_round_rows,
    parse_is_moab,
    parse_number,
    split_bloon_name,
)
from btd6.rounds import get_round, get_round_summary, row_to_group, validate_round


@pytest.fixture
def connection() -> sqlite3.Connection:
    conn = connect(":memory:")
    initialize_database(conn)
    return conn


def bloon_row(name: str, rbe: int | None, is_moab: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "health": 1,
        "health_fort": None,
        "layers": 1,
        "rbe": rbe,
        "rbe_fort": None,
        "is_moab": is_moab,
        "speed": 1.0,
    }


def test_validate_round_type_error_message(connection) -> None:
    with pytest.raises(TypeError, match="round_number must be an int, got str"):
        validate_round(connection, "5")


def test_row_to_group_maps_every_field_distinctly() -> None:
    first = row_to_group((0, "Red", 0, 1, 0, 4, 0, 0, 1, 0))
    second = row_to_group((1, "Blue", 1, 0, 1, 6, 1.5, 7.25, None, 1))
    assert (first.is_regrow, first.is_fortified, first.start, first.duration) == (
        True,
        False,
        0,
        0,
    )
    assert (second.is_regrow, second.is_fortified, second.start, second.duration) == (
        False,
        True,
        1.5,
        7.25,
    )


def test_summary_total_rbe_treats_null_rbe_as_zero(connection) -> None:
    load_bloons(connection, [bloon_row("Red", 1), bloon_row("Mystery", None)])
    ids = {name: ident for name, ident in connection.execute("SELECT name, id FROM bloons")}
    rows = [
        {"round": 1, "group_index": 0, "bloon": "Red", "count": 2, "start": 0, "duration": 1},
        {"round": 1, "group_index": 1, "bloon": "Mystery", "count": 5, "start": 0, "duration": 1},
    ]
    load_rounds(connection, rows, ids)
    assert get_round(connection, 1)[1].rbe is None
    assert get_round_summary(connection, 1).total_rbe == 2


def test_extract_round_rows_requires_rounds_list() -> None:
    with pytest.raises(ValueError, match=r'^roundset has no "rounds" list$'):
        extract_round_rows({})


def test_build_group_rows_without_bloon_groups() -> None:
    assert build_group_rows(1, {}) == []


def test_parse_number_non_numeric_message() -> None:
    with pytest.raises(ValueError) as error:
        parse_number({"x": "abc"}, "x", int)
    assert str(error.value) == "Bloon '' has non-numeric x: 'abc'"


def test_parse_is_moab_invalid_message() -> None:
    with pytest.raises(ValueError) as error:
        parse_is_moab({"id": "Red", "is_moab": "maybe"})
    assert str(error.value) == "Bloon 'Red' has invalid is_moab: \"maybe\""


def test_extract_bloon_row_empty_name_message() -> None:
    with pytest.raises(ValueError) as error:
        extract_bloon_row({"id": "  "})
    assert str(error.value) == "Bloon row has an empty name (Cargo id)"


def test_split_bloon_name_empty_message() -> None:
    with pytest.raises(ValueError) as error:
        split_bloon_name("")
    assert str(error.value) == "Cannot split an empty bloon name"


def test_split_bloon_name_no_base_message() -> None:
    with pytest.raises(ValueError) as error:
        split_bloon_name("Camo")
    assert str(error.value) == "Bloon name 'Camo' has no base bloon"


def test_cargo_rows_error_message() -> None:
    with pytest.raises(ValueError) as error:
        fetch.cargo_rows({"error": "boom"})
    assert str(error.value) == "Wiki cargo query failed: boom"


@pytest.mark.parametrize("response", [{}, {"cargoquery": []}])
def test_cargo_rows_empty(response) -> None:
    with pytest.raises(ValueError) as error:
        fetch.cargo_rows(response)
    assert str(error.value) == "Wiki cargo query returned no rows"


def test_fetch_bloons_empty_response(monkeypatch) -> None:
    monkeypatch.setattr(fetch, "wiki_api", lambda **params: {})
    with pytest.raises(ValueError) as error:
        fetch.fetch_bloons()
    assert str(error.value) == "Wiki cargo query returned no rows"


def test_fetch_bloons_error_message(monkeypatch) -> None:
    monkeypatch.setattr(fetch, "wiki_api", lambda **params: {"error": "boom"})
    with pytest.raises(ValueError) as error:
        fetch.fetch_bloons()
    assert str(error.value) == "Wiki cargo query failed: boom"


def test_fetch_bloons_three_pages_offsets(monkeypatch) -> None:
    limit = fetch.CARGO_PAGE_LIMIT
    offsets: list[int] = []
    sizes = iter([limit, limit, 1])

    def fake_api(**params: Any) -> dict[str, Any]:
        offsets.append(params["offset"])
        return {"cargoquery": [{"title": {"id": "Red"}} for _ in range(next(sizes))]}

    monkeypatch.setattr(fetch, "wiki_api", fake_api)
    rows = fetch.fetch_bloons()
    assert offsets == [0, limit, 2 * limit]
    assert len(rows) == 2 * limit + 1


IS_MOAB_INDEX = 1 + BLOON_COLUMNS.index("is_moab")


@pytest.mark.parametrize("value", [True, 1])
def test_bloon_params_truthy_is_moab_is_int_one(value) -> None:
    result = bloon_params(bloon_row("Moab", 616, value))[IS_MOAB_INDEX]
    assert result == 1
    assert type(result) is int


@pytest.mark.parametrize("value", [False, 0])
def test_bloon_params_falsy_is_moab_is_int_zero(value) -> None:
    result = bloon_params(bloon_row("Red", 1, value))[IS_MOAB_INDEX]
    assert result == 0
    assert type(result) is int
