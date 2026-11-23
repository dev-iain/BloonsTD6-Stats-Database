from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pytest

from btd6.ui.palettes import DARK, LIGHT, Palette
from btd6.ui.presenters import TABLE_COLUMNS, FilterInputs, PopChoice
from btd6.ui.theme import Fonts, apply_theme, build_fonts
from btd6.ui.widgets.filter_panel import FilterPanel, is_partial_number
from btd6.ui.widgets.results_table import ASCENDING_MARK, DESCENDING_MARK, ResultsTable

SAMPLE_ROW = ("Super Monkey", "0-0-0", "0.045", "1", "1", "1", "200", "Bk Wh")


@pytest.fixture
def fonts(tk_root: tk.Tk) -> Fonts:
    built = build_fonts(tk_root)
    apply_theme(tk_root, LIGHT, built)
    return built


@pytest.fixture
def table(tk_root: tk.Tk, fonts: Fonts) -> ResultsTable:
    sorted_columns: list[str] = []
    widget = ResultsTable(tk_root, fonts, sorted_columns.append, lambda: None)
    widget.apply_palette(LIGHT)
    widget.sorted_columns = sorted_columns
    widget.grid()
    tk_root.update_idletasks()
    return widget


@pytest.fixture
def panel(tk_root: tk.Tk, fonts: Fonts) -> FilterPanel:
    events: dict[str, list] = {"change": [], "submit": [], "reset": []}
    widget = FilterPanel(
        tk_root,
        events["change"].append,
        events["submit"].append,
        lambda: events["reset"].append(True),
    )
    widget.events = events
    widget.grid()
    tk_root.update_idletasks()
    return widget


def tags_of(table: ResultsTable) -> list[tuple]:
    return [table._tree.item(item, "tags") for item in table._tree.get_children()]


def test_set_rows_inserts_in_order_with_zebra_tags(table: ResultsTable) -> None:
    table.set_rows([SAMPLE_ROW, SAMPLE_ROW, SAMPLE_ROW])
    assert table.row_values() == [SAMPLE_ROW, SAMPLE_ROW, SAMPLE_ROW]
    assert tags_of(table) == [("even",), ("odd",), ("even",)]


def test_set_rows_replaces_previous_rows(table: ResultsTable) -> None:
    table.set_rows([SAMPLE_ROW] * 5)
    table.set_rows([SAMPLE_ROW])
    assert len(table.row_values()) == 1


def test_large_result_set_loads(table: ResultsTable) -> None:
    table.set_rows([SAMPLE_ROW] * 800)
    assert len(table.row_values()) == 800


def test_numeric_columns_right_aligned(table: ResultsTable) -> None:
    for spec in TABLE_COLUMNS:
        anchor = str(table._tree.column(spec.key, "anchor"))
        assert anchor == ("e" if spec.numeric else "w")


def test_heading_click_emits_only_for_sortable_columns(table: ResultsTable) -> None:
    for spec in TABLE_COLUMNS:
        command = table._tree.heading(spec.key, "command")
        assert bool(command) == spec.sortable


def test_sort_indicator_shown_and_moves(table: ResultsTable) -> None:
    table.set_sort_indicator("attack_rate", False)
    assert table._tree.heading("attack_rate", "text").endswith(ASCENDING_MARK)
    table.set_sort_indicator("attack_rate", True)
    assert table._tree.heading("attack_rate", "text").endswith(DESCENDING_MARK)
    table.set_sort_indicator("path", False)
    assert not table._tree.heading("attack_rate", "text").endswith(DESCENDING_MARK)


def test_placeholder_shows_message_and_optional_load(table: ResultsTable) -> None:
    table.show_placeholder("Nothing here", offer_load=True)
    assert table._placeholder.winfo_manager() == "grid"
    assert table._placeholder_label.cget("text") == "Nothing here"
    assert table._load_button.winfo_manager() == "grid"
    table.show_placeholder("Empty", offer_load=False)
    assert table._load_button.winfo_manager() == ""
    table.set_rows([SAMPLE_ROW])
    assert table._placeholder.winfo_manager() == ""


def test_load_button_can_be_disabled(table: ResultsTable) -> None:
    table.set_load_enabled(False)
    assert table._load_button.instate(["disabled"])


def test_table_scrollbars_wired_both_ways(table: ResultsTable) -> None:
    assert table._tree.cget("yscrollcommand")
    assert table._tree.cget("xscrollcommand")


def test_table_grid_is_resizable(table: ResultsTable) -> None:
    assert table.grid_columnconfigure(0)["weight"] == 1
    assert table.grid_rowconfigure(0)["weight"] == 1


def test_treeview_row_height_meets_target(table: ResultsTable) -> None:
    assert int(ttk.Style(table).lookup("Stats.Treeview", "rowheight")) >= 20


def test_panel_defaults_round_trip(panel: FilterPanel) -> None:
    assert panel.get_inputs() == FilterInputs()


def test_panel_set_inputs_does_not_emit_change(panel: FilterPanel) -> None:
    panel.set_inputs(FilterInputs(name_text="dart", min_pierce="4"))
    assert panel.events["change"] == []
    assert panel.get_inputs().name_text == "dart"
    assert panel.get_inputs().min_pierce == "4"


def test_panel_emits_change_on_edit(panel: FilterPanel) -> None:
    panel.name_var.set("wiz")
    panel.choice_vars["lead"].set(PopChoice.CAN)
    assert [item.name_text for item in panel.events["change"]] == ["wiz", "wiz"]
    assert panel.events["change"][-1].pops["lead"] == PopChoice.CAN


def test_panel_buttons_emit_submit_and_reset(panel: FilterPanel) -> None:
    panel.search_button.invoke()
    panel.reset_button.invoke()
    assert len(panel.events["submit"]) == 1
    assert panel.events["reset"] == [True]


def focus_entry(tk_root: tk.Tk, entry: ttk.Entry) -> None:
    tk_root.deiconify()
    tk_root.update()
    entry.focus_force()
    tk_root.update()


def test_escape_clears_name(panel: FilterPanel, tk_root: tk.Tk) -> None:
    panel.name_var.set("abc")
    focus_entry(tk_root, panel.name_entry)
    panel.name_entry.event_generate("<Escape>")
    assert panel.name_var.get() == ""


def test_return_in_entry_submits(panel: FilterPanel, tk_root: tk.Tk) -> None:
    focus_entry(tk_root, panel.name_entry)
    panel.name_entry.event_generate("<Return>")
    assert len(panel.events["submit"]) == 1


def test_errors_show_text_and_invalid_state(panel: FilterPanel) -> None:
    panel.set_errors({"min_pierce": "Pierce must be a number"})
    assert panel._error_labels["min_pierce"].cget("text") == "Pierce must be a number"
    assert panel._entries["min_pierce"].instate(["invalid"])
    panel.set_errors({})
    assert not panel._entries["min_pierce"].instate(["invalid"])
    assert panel._error_labels["min_pierce"].cget("text") == ""


@pytest.mark.parametrize(
    ("text", "is_valid"),
    [
        ("", True),
        ("12", True),
        ("1.5", True),
        (".", True),
        ("-1", False),
        ("a", False),
        ("1e5", False),
    ],
)
def test_partial_number_validation(text: str, is_valid: bool) -> None:
    assert is_partial_number(text) is is_valid


def test_numeric_entry_rejects_letters(panel: FilterPanel) -> None:
    entry = panel._entries["min_damage"]
    entry.insert(0, "abc")
    assert panel.threshold_vars["min_damage"].get() == ""
    entry.insert(0, "12")
    assert panel.threshold_vars["min_damage"].get() == "12"


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=lambda palette: palette.name)
def test_every_custom_style_has_interactive_states(
    tk_root: tk.Tk, fonts: Fonts, palette: Palette
) -> None:
    apply_theme(tk_root, palette, fonts)
    style = ttk.Style(tk_root)
    for name in ("Action.TButton", "Secondary.TButton"):
        mapped = {key for key, _ in _all_maps(style, name)}
        assert {"disabled", "pressed", "active"} <= mapped


def _all_maps(style: ttk.Style, name: str) -> list[tuple[str, str]]:
    pairs = []
    for option in ("background", "foreground"):
        for entry in style.map(name, option):
            pairs.extend((state, entry[-1]) for state in entry[:-1])
    return pairs


def test_theme_switch_changes_treeview_background(tk_root: tk.Tk, fonts: Fonts) -> None:
    style = ttk.Style(tk_root)
    apply_theme(tk_root, DARK, fonts)
    assert style.lookup("Stats.Treeview", "background") == DARK.color_surface
    apply_theme(tk_root, LIGHT, fonts)
    assert style.lookup("Stats.Treeview", "background") == LIGHT.color_surface


def test_fonts_at_least_ten_points(fonts: Fonts) -> None:
    assert abs(fonts.body.cget("size")) >= 10
