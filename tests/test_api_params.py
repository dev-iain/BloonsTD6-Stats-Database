from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6.api.params import form_to_filters, form_to_search_options, rows_to_cells
from btd6.formatting import TABLE_CELL_COLUMNS, format_cell, format_row
from btd6.query import POP_PROPERTIES, SORT_COLUMNS, QueryError, UpgradeFilters
from tests.factories import ResultRowFactory

TABLE_WIDTH = len(TABLE_CELL_COLUMNS) + 1


def base_form(**overrides: str | bool) -> dict[str, str | bool]:
    form: dict[str, str | bool] = {
        "name": "",
        "camo": "either",
        "min_range": "",
        "min_pierce": "",
        "min_damage": "",
        "min_speed": "",
        "damage_type": "Any",
        "sort": "",
        "limit": "",
        **{prop: "any" for prop in POP_PROPERTIES},
    }
    form.update(overrides)
    return form


# region form_to_filters


def test_form_to_filters_all_base() -> None:
    assert form_to_filters(base_form()) == UpgradeFilters()


@pytest.mark.parametrize(
    ("name", "expected"),
    [("wizard", "wizard"), ("  wizard  ", "wizard"), ("   ", None), ("", None)],
    ids=["text", "padded", "only_spaces", "blank"],
)
def test_form_to_filters_name_text(name: str, expected: str | None) -> None:
    assert form_to_filters(base_form(name=name)).tower_name_contains == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("3", 3.0), ("0", 0.0), ("2.5", 2.5), ("", None), ("  ", None)],
    ids=["positive", "zero", "fraction", "blank", "only_spaces"],
)
def test_form_to_filters_number_valid(text: str, expected: float | None) -> None:
    assert form_to_filters(base_form(min_pierce=text)).min_pierce == expected


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("abc", "min_pierce must be a number, got 'abc'"),
        ("-1", "min_pierce must be 0 or more, got -1.0"),
        ("inf", "min_pierce must be a number, got 'inf'"),
        ("nan", "min_pierce must be a number, got 'nan'"),
    ],
    ids=["not_a_number", "negative", "infinite", "nan"],
)
def test_form_to_filters_number_invalid(text: str, message: str) -> None:
    with pytest.raises(QueryError) as excinfo:
        form_to_filters(base_form(min_pierce=text))
    assert str(excinfo.value) == message


@pytest.mark.parametrize(
    ("form_key", "filter_field"),
    [
        ("min_range", "min_range"),
        ("min_pierce", "min_pierce"),
        ("min_damage", "min_damage"),
        ("min_speed", "min_projectile_speed"),
    ],
)
def test_form_to_filters_each_numeric_field(form_key: str, filter_field: str) -> None:
    assert getattr(form_to_filters(base_form(**{form_key: "3"})), filter_field) == 3.0
    with pytest.raises(QueryError, match=form_key):
        form_to_filters(base_form(**{form_key: "-1"}))


@pytest.mark.parametrize(
    ("choice", "expected"),
    [("any", None), ("can", True), ("cannot", False), (False, None), (True, True)],
    ids=["any", "can", "cannot", "unchecked", "checked"],
)
def test_form_to_filters_pop_choice(choice: str | bool, expected: bool | None) -> None:
    assert form_to_filters(base_form(lead=choice)).can_pop_lead is expected


def test_form_to_filters_pop_unknown_text() -> None:
    with pytest.raises(QueryError) as excinfo:
        form_to_filters(base_form(lead="maybe"))
    assert str(excinfo.value) == 'lead must be any, can or cannot, got "maybe"'


def test_form_to_filters_all_checkboxes_unchecked() -> None:
    form = base_form(**{prop: False for prop in POP_PROPERTIES})
    assert form_to_filters(form) == UpgradeFilters()


@pytest.mark.parametrize("prop", POP_PROPERTIES)
def test_form_to_filters_pop_maps_each_property(prop: str) -> None:
    filters = form_to_filters(base_form(**{prop: "cannot"}))
    assert getattr(filters, f"can_pop_{prop}") is False
    others = [getattr(filters, f"can_pop_{name}") for name in POP_PROPERTIES if name != prop]
    assert others == [None] * (len(POP_PROPERTIES) - 1)


@pytest.mark.parametrize(("camo", "expected"), [("either", None), ("yes", True), ("no", False)])
def test_form_to_filters_camo(camo: str, expected: bool | None) -> None:
    assert form_to_filters(base_form(camo=camo)).can_hit_camo is expected


def test_form_to_filters_camo_unknown_text() -> None:
    with pytest.raises(QueryError) as excinfo:
        form_to_filters(base_form(camo="maybe"))
    assert str(excinfo.value) == 'camo must be either, yes or no, got "maybe"'


@pytest.mark.parametrize(("text", "expected"), [("Any", None), ("Plasma", "Plasma"), ("", None)])
def test_form_to_filters_damage_type(text: str, expected: str | None) -> None:
    assert form_to_filters(base_form(damage_type=text)).damage_type == expected


def test_form_to_filters_empty_form() -> None:
    assert form_to_filters({}) == UpgradeFilters()


def test_form_to_filters_epic_example() -> None:
    filters = form_to_filters(base_form(lead="cannot", min_pierce="3"))
    assert filters == UpgradeFilters(can_pop_lead=False, min_pierce=3.0)


@given(st.text())
def test_form_to_filters_never_leaks_other_exceptions(text: str) -> None:
    try:
        filters = form_to_filters(base_form(min_pierce=text))
    except QueryError:
        return
    assert filters.min_pierce is None or filters.min_pierce >= 0


# endregion

# region form_to_search_options


def test_form_to_search_options_all_base() -> None:
    assert form_to_search_options(base_form()) == (None, None)


def test_form_to_search_options_sort_allowed() -> None:
    assert form_to_search_options(base_form(sort="projectile_pierce")) == (
        "projectile_pierce",
        None,
    )


@pytest.mark.parametrize("column", SORT_COLUMNS)
def test_form_to_search_options_accepts_every_sort_column(column: str) -> None:
    assert form_to_search_options(base_form(sort=column))[0] == column


def test_form_to_search_options_sort_not_allowed() -> None:
    with pytest.raises(QueryError) as excinfo:
        form_to_search_options(base_form(sort="bogus"))
    assert str(excinfo.value).startswith('Cannot sort by "bogus". Allowed:')


@pytest.mark.parametrize(("text", "expected"), [("1", 1), ("500", 500), ("", None)])
def test_form_to_search_options_limit_valid(text: str, expected: int | None) -> None:
    assert form_to_search_options(base_form(limit=text)) == (None, expected)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("0", "limit must be at least 1, got 0"),
        ("-3", "limit must be at least 1, got -3"),
        ("abc", "limit must be a whole number, got 'abc'"),
        ("2.5", "limit must be a whole number, got '2.5'"),
    ],
    ids=["zero", "negative", "not_a_number", "fractional"],
)
def test_form_to_search_options_limit_invalid(text: str, message: str) -> None:
    with pytest.raises(QueryError) as excinfo:
        form_to_search_options(base_form(limit=text))
    assert str(excinfo.value) == message


# endregion

# region rows_to_cells

BASE_CELLS = ("Super Monkey", "0-0-0", "0.045", "1", "2", "3", "200", "All")


def build_row(path: str = "0-0-0", **overrides: Any) -> dict[str, Any]:
    return ResultRowFactory(path=path, **overrides)


def test_rows_to_cells_all_base() -> None:
    assert rows_to_cells([build_row()]) == [BASE_CELLS]


def test_rows_to_cells_no_rows() -> None:
    assert rows_to_cells([]) == []


def test_rows_to_cells_several_rows_keep_order() -> None:
    cells = rows_to_cells([build_row("0-0-0"), build_row("1-1-0")])
    assert [row[1] for row in cells] == ["0-0-0", "1-1-0"]


@pytest.mark.parametrize(
    ("overrides", "index", "expected"),
    [
        ({"projectile_pierce": None}, 5, "-"),
        ({"projectile_pierce": 0.5}, 5, "0.5"),
        ({"attack_rate": 1.0}, 2, "1"),
    ],
    ids=["null_stat", "fractional_stat", "whole_float_rate"],
)
def test_rows_to_cells_stat_cells(overrides: dict[str, Any], index: int, expected: str) -> None:
    assert rows_to_cells([build_row(**overrides)])[0][index] == expected


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({f"can_pop_{prop}": 0 for prop in POP_PROPERTIES}, "-"),
        ({"can_pop_lead": 0, "can_pop_black": 0, "can_pop_white": 0, "can_pop_purple": 0}, "Gl Fr"),
        (
            {f"can_pop_{prop}": 0 for prop in POP_PROPERTIES if prop not in ("lead", "glass")},
            "Ld Gl",
        ),
        ({f"can_pop_{prop}": None for prop in POP_PROPERTIES}, "-"),
    ],
    ids=["none", "last_two", "lead_and_glass", "null_flags"],
)
def test_rows_to_cells_pops_cell(overrides: dict[str, Any], expected: str) -> None:
    assert rows_to_cells([build_row(**overrides)])[0][-1] == expected


def test_format_cell_flags_yes_no() -> None:
    assert format_cell("can_hit_camo", 1) == "yes"
    assert format_cell("can_hit_camo", 0) == "no"
    assert format_cell("can_hit_camo", None) == "-"


@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "projectile_pierce": st.one_of(st.none(), st.floats(0, 1000), st.integers(0, 99)),
                "attack_rate": st.floats(0.001, 10),
                "can_pop_lead": st.sampled_from([0, 1, None]),
            }
        ),
        max_size=5,
    )
)
def test_rows_to_cells_shape_invariant(overrides: list[dict[str, Any]]) -> None:
    rows = [build_row(**item) for item in overrides]
    cells = rows_to_cells(rows)
    assert len(cells) == len(rows)
    assert all(len(row) == TABLE_WIDTH for row in cells)
    assert all(isinstance(cell, str) for row in cells for cell in row)
    assert cells == [format_row(row) for row in rows]


# endregion
