from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path

import pytest

from btd6.ui.app import AppWindow
from btd6.ui.palettes import DARK
from btd6.ui.presenters import PopChoice
from tests.test_query import build_database


def pump(root: tk.Tk, until: Callable[[], object], timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not until() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    assert until(), "condition not reached"


def run_inline(target: Callable[[], None]) -> None:
    target()


@pytest.fixture
def database_path(tmp_path: Path, golden_csv_path: Path) -> str:
    path = str(tmp_path / "app.db")
    connection = build_database(golden_csv_path, all_rows=True, path=path)
    connection.commit()
    connection.close()
    return path


def make_window(tk_root: tk.Tk, path: str) -> AppWindow:
    window = AppWindow(tk_root, path, start_thread=run_inline)
    window.start()
    return window


def test_startup_fills_table_from_database(tk_root: tk.Tk, database_path: str) -> None:
    window = make_window(tk_root, database_path)
    pump(tk_root, lambda: window.view.results_table.row_values())
    assert window.view.status_var.get().endswith("upgrades")


def test_missing_database_shows_empty_state_with_load(tk_root: tk.Tk, tmp_path: Path) -> None:
    window = make_window(tk_root, str(tmp_path / "none.db"))
    pump(tk_root, lambda: window.view.status_var.get() == "Database not loaded")
    table = window.view.results_table
    assert table._load_button.winfo_manager() == "grid"
    assert not (tmp_path / "none.db").exists()


def test_sort_click_updates_indicator_and_order(tk_root: tk.Tk, database_path: str) -> None:
    window = make_window(tk_root, database_path)
    pump(tk_root, lambda: window.view.results_table.row_values())
    window.presenter.on_sort("projectile_damage")
    window.presenter.on_sort("projectile_damage")
    pump(tk_root, lambda: window.view.results_table._descending)
    heading = window.view.results_table._tree.heading("projectile_damage", "text")
    assert heading.endswith("▼")


def test_filter_change_is_debounced_then_applied(tk_root: tk.Tk, database_path: str) -> None:
    window = make_window(tk_root, database_path)
    pump(tk_root, lambda: window.view.results_table.row_values())
    total = len(window.view.results_table.row_values())
    window.view.filter_panel.choice_vars["lead"].set(PopChoice.CAN)
    assert len(window.view.results_table.row_values()) == total
    pump(tk_root, lambda: len(window.view.results_table.row_values()) != total)


def test_invalid_number_never_searches_and_flags_field(tk_root: tk.Tk, database_path: str) -> None:
    window = make_window(tk_root, database_path)
    pump(tk_root, lambda: window.view.results_table.row_values())
    window.view.filter_panel.threshold_vars["min_pierce"].set(".")
    window.view.filter_panel.search_button.invoke()
    assert window.view.filter_panel._entries["min_pierce"].instate(["invalid"])
    assert window.view.status_is_error


def test_impossible_filter_shows_empty_state(tk_root: tk.Tk, database_path: str) -> None:
    window = make_window(tk_root, database_path)
    pump(tk_root, lambda: window.view.results_table.row_values())
    window.view.filter_panel.threshold_vars["min_damage"].set("999999")
    window.view.filter_panel.search_button.invoke()
    pump(tk_root, lambda: window.view.status_var.get() == "No upgrades match these filters.")
    assert window.view.results_table._placeholder.winfo_manager() == "grid"


def test_reset_clears_filters(tk_root: tk.Tk, database_path: str) -> None:
    window = make_window(tk_root, database_path)
    window.view.filter_panel.threshold_vars["min_damage"].set("5")
    window.view.filter_panel.reset_button.invoke()
    assert window.view.filter_panel.threshold_vars["min_damage"].get() == ""


def test_dark_mode_toggle_switches_palette(tk_root: tk.Tk, database_path: str) -> None:
    window = make_window(tk_root, database_path)
    window.view.dark_toggle.invoke()
    from tkinter import ttk

    assert ttk.Style(tk_root).lookup("Stats.Treeview", "background") == DARK.color_surface


def test_close_destroys_window_without_pending_errors(tk_root: tk.Tk, database_path: str) -> None:
    window = make_window(tk_root, database_path)
    window.close()
    with pytest.raises(tk.TclError):
        tk_root.winfo_exists()
