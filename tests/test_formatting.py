from __future__ import annotations

import pytest

from btd6 import cli, formatting
from btd6.query import POP_PROPERTIES
from btd6.ui.presenters import TABLE_COLUMNS

SAMPLE_ROW = {
    "tower_name": "Super Monkey",
    "path": "0-2-3",
    "attack_rate": 0.045,
    "projectile_count": 1,
    "projectile_damage": 2.0,
    "projectile_pierce": None,
    "projectile_speed": 200.0,
    **{f"can_pop_{name}": 0 for name in POP_PROPERTIES},
}


@pytest.mark.parametrize(
    ("column", "value", "expected"),
    [
        ("path", None, "-"),
        ("can_pop_lead", 1, "yes"),
        ("can_hit_camo", 0, "no"),
        ("projectile_damage", 2.0, "2"),
        ("attack_rate", 0.045, "0.045"),
        ("path", "0-1-2", "0-1-2"),
    ],
)
def test_format_cell(column: str, value: object, expected: object) -> None:
    assert formatting.format_cell(column, value) == expected


def test_cli_reexports_shared_formatting() -> None:
    assert cli.format_cell is formatting.format_cell
    assert cli.RESULT_COLUMNS is formatting.RESULT_COLUMNS
    assert cli.EMPTY_RESULTS_MESSAGE == formatting.EMPTY_RESULTS_MESSAGE


def test_pops_summary_lists_codes_in_order() -> None:
    popped_row = {**SAMPLE_ROW, "can_pop_lead": 1, "can_pop_glass": 1}
    assert formatting.pops_summary(popped_row) == "Ld Gl"


def test_pops_summary_none_and_all() -> None:
    assert formatting.pops_summary(SAMPLE_ROW) == "-"
    assert (
        formatting.pops_summary({**SAMPLE_ROW, **{f"can_pop_{name}": 1 for name in POP_PROPERTIES}})
        == "All"
    )


def test_format_row_matches_columns_and_formats_values() -> None:
    cells = formatting.format_row(SAMPLE_ROW)
    assert len(cells) == len(TABLE_COLUMNS)
    assert cells == ("Super Monkey", "0-2-3", "0.045", "1", "2", "-", "200", "-")


def test_table_cell_columns_match_presenter_columns() -> None:
    assert formatting.TABLE_CELL_COLUMNS == tuple(spec.key for spec in TABLE_COLUMNS[:-1])
