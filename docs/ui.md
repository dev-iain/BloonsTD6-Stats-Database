# Desktop UI

Run with `uv run python -m btd6 ui` (honors `--db`) or `uv run python -m btd6.ui`. Stdlib `tkinter`/`ttk` only. With no display or no tkinter the command prints a friendly message and exits 1.

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

1. `uv run python -m btd6 ui` opens a window; the first paint is sharp at 100%, 150% and 200% display scaling (DPI awareness is requested in `enable_dpi_awareness`).
2. Text is at least 10 pt and row height is at least about 32 px at every scale.
3. Light and dark palettes: every control is legible; focus rings are visible on entries, radio buttons, buttons and the checkbox; hover and pressed states change on buttons.
4. Tab visits name, radios, number fields, Reset, Search, the table, in visual order.
5. With no `btd6.db`: empty state with a Load button; Load shows per-tower progress and refreshes the table; unplugging the network shows a readable error and no traceback.
6. Resize to the minimum size: nothing is clipped; scrollbars appear on the table.
7. Hover the "Attack rate (s)" and "Pops" headers for the tooltips.
8. Closing the window mid-load exits cleanly.
