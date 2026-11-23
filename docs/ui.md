# Desktop UI

Run with `uv run python -m btd6 gui` (honors `--db`; `ui` is kept as an alias) or `uv run python -m btd6.ui`. Stdlib `tkinter`/`ttk` only. With no display or no tkinter the command prints a friendly message and exits 1.

## Tabs

The window is a `ttk.Notebook` built by `btd6.ui.app.build_window(db_path)`; `main(db_path)` runs it and closes its SQLite connection when the window closes (the CLI `gui` command reaches it through `btd6.ui.launcher.launch`).

- Search (Alt+S is search; the tab is `SearchTab` in `search_tab.py`): filters, a Sort by combobox (the `SORT_COLUMNS` list, kept in sync with header clicks), a damage type combobox filled by `list_damage_types`, and a Limit spinbox.
- Rounds and Rankings: "Coming soon" placeholders until the round-data and rankings epics land.

`btd6/ui/search_viewmodel.py` holds the pure form parsing (`form_to_filters`, `form_to_search_options`, `rows_to_cells`) shared with the presenter.

## Structure

- `btd6/ui/presenters.py`, `worker.py`, `scheduler.py`, `palettes.py`, `services.py`: no tkinter import (tested in a subprocess).
- `btd6/ui/theme.py`: fonts, ttk styles, DPI awareness (the only platform branch).
- `btd6/ui/widgets/`, `views/`, `app.py`: Tk code. Views are passive; `SearchPresenter` owns filter state, debounce (250 ms), stale-result dropping and sort state.
- All sorting and filtering happens in SQL through `search_upgrades`. First header click sorts ascending, second descending.
- Queries and the load pipeline run on a worker thread with their own SQLite connection; results return through `BackgroundRunner`, polled with `after`.

## Keyboard

Alt+S search, Alt+R reset, Alt+N or Ctrl+F focus the name filter, Alt+L load data, Alt+D dark mode, Ctrl+1..8 sort by column N (headings are not keyboard reachable in ttk), Ctrl+Q quit, Escape clears the name filter, Enter in an entry searches.

## Manual Windows checklist

No Windows machine was available during development. Verify by hand:

1. `uv run python -m btd6 gui` opens a window; the first paint is sharp at 100%, 150% and 200% display scaling (DPI awareness is requested in `enable_dpi_awareness`).
2. Text is at least 10 pt and row height is at least about 32 px at every scale.
3. Light and dark palettes: every control is legible; focus rings are visible on entries, radio buttons, buttons and the checkbox; hover and pressed states change on buttons.
4. Tab visits name, radios, number fields, Reset, Search, the table, in visual order.
5. With no `btd6.db`: empty state with a Load button; Load shows per-tower progress and refreshes the table; unplugging the network shows a readable error and no traceback.
6. Resize to the minimum size: nothing is clipped; scrollbars appear on the table.
7. Hover the "Attack rate (s)" and "Pops" headers for the tooltips.
8. Closing the window mid-load exits cleanly.
