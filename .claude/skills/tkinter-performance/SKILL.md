---
name: tkinter-performance
description: Tkinter/ttk patterns for a responsive desktop UI over SQLite: keeping the mainloop free, fast Treeview tables, lazy loading, startup time, and measuring frame and interaction latency. Use when building or tuning anything in btd6/ui.
---

# Tkinter Performance

Tkinter is single-threaded: one mainloop handles drawing, input, and your callbacks. Anything slow in a callback freezes the window. Treat the mainloop like a render thread and keep it free.

## Responsiveness Budgets

| Metric | Good | Needs work | Poor |
| --- | --- | --- | --- |
| Startup to first window shown | <500ms | 0.5-1.5s | >1.5s |
| Input latency (click, keypress to visible response) | <100ms | 100-300ms | >300ms |
| Search with filters to table populated | <200ms | 200-600ms | >600ms |
| Longest single callback blocking the mainloop | <50ms | 50-100ms | >100ms |
| Window resize (no visible stutter or flicker) | smooth | occasional lag | redraw tearing |

## Keep the Mainloop Free

Rules:

- Never call `time.sleep`, blocking I/O, or long loops in a callback.
- Never touch widgets from a worker thread. Workers put results on a `queue.Queue`; the main thread polls it with `after`.
- Use `after(ms, fn)` for deferred and chunked work, and `after_cancel` when it is superseded.
- Call `update_idletasks()` sparingly to flush geometry. Avoid `update()` inside callbacks because it reenters the event loop.

```python
from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from typing import Any

POLL_INTERVAL_MS = 50


class BackgroundTask:
    def __init__(
        self, root: tk.Misc, work: Callable[[], Any], on_done: Callable[[Any], None]
    ) -> None:
        self._results: queue.Queue[Any] = queue.Queue()
        self._root = root
        self._on_done = on_done
        threading.Thread(target=lambda: self._results.put(work()), daemon=True).start()
        self._poll()

    def _poll(self) -> None:
        try:
            self._on_done(self._results.get_nowait())
        except queue.Empty:
            self._root.after(POLL_INTERVAL_MS, self._poll)
```

SQLite connections cannot be shared across threads by default. Open a new connection inside the worker via `btd6.db.connection.connect`, or never share the main one.

## Fast Queries

- Queries live in `btd6.query`; the UI only calls them. Push filtering, sorting, and limiting into SQL rather than into Python loops over every row.
- Select only the columns the table displays.
- Check query plans with `EXPLAIN QUERY PLAN`; add indexes through the `schema-change` skill when a filter column scans the full table.
- Cache the results of lookup tables (damage types, tower names) once at startup rather than per search.
- Debounce text filters (about 250ms) with `after_cancel`/`after`, and drop results from stale searches by tagging each request with an incrementing id.

## Populating Treeview

`ttk.Treeview` is fast for hundreds of rows and degrades into the thousands when each insert triggers a redraw.

- Clear with a single `delete(*tree.get_children())` call.
- Insert in one pass, with `tree.insert("", "end", values=...)`; do not call `update()` between rows.
- Above about 2,000 rows, insert in chunks of 200-500 via `after(1, ...)` so input stays responsive, or paginate.
- Avoid per-row `tag_configure` or `item(...)` calls inside the loop. Configure a small fixed set of tags (for example `even`/`odd`) once, and pass `tags=` at insert time.
- Precompute display strings in the presenter; no formatting work inside the insert loop beyond a tuple lookup.
- Sort by re-querying or sorting the in-memory list once, then repopulating. Never sort via repeated `move` calls.

## Startup Time

- Import heavy modules lazily: `pandas` and `matplotlib` only when the screen that needs them opens.
- Build the main window first and call `root.update_idletasks()`, then create secondary tabs and dialogs on first use.
- Show the window before loading data; fill the table from a background task and show a status message while it loads.
- Create expensive widgets (large `Treeview`, `Canvas` charts) once and reuse them. Hide and show rather than destroy and recreate.
- Profile with `python -X importtime -m btd6` to find slow imports.

## Canvas and Redraws

- Update existing canvas items with `itemconfigure`/`coords` rather than deleting and recreating everything.
- Group items with tags; hide with `state="hidden"` rather than deleting.
- Throttle `<Configure>` handlers: resize events fire continuously, so debounce them with `after_idle` or `after` and redraw once.
- Avoid animating with tight `after(1, ...)` loops; 16ms (about 60fps) is the floor, and most UI needs none.

## Layout Stability

- Fix widths for columns and entries (`width=`, `Treeview.column(..., width=, stretch=)`) so content changes do not reflow the window.
- Reserve space for status and error text with a permanent label rather than packing and unpacking it, which shifts everything below.
- Do not change geometry managers or `grid_remove` and re-add large frames on every update; toggle contents instead.
- Set `minsize` on the root and weights on containers once at construction.

## Fonts and Images

- Create `tkinter.font.Font` objects once in `theme.py` and share them. Do not construct fonts per widget.
- Keep a reference to every `PhotoImage` (attribute on the widget or a module-level cache), or Tk garbage-collects it and the image disappears.
- Pre-scale images to display size at load, not on every redraw. Use `PhotoImage.subsample`/`zoom` or Pillow once and cache the result.
- Limit to 2 font families.

## Measuring

Measure real interactions, not guesses:

```python
import time
from collections.abc import Callable
from functools import wraps


def log_slow(threshold_ms: float = 50.0) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            if elapsed_ms > threshold_ms:
                print(f"SLOW {func.__qualname__}: {elapsed_ms:.1f}ms")
            return result

        return wrapper

    return decorator
```

- Wrap suspect callbacks with `log_slow` during development; any callback over the 50ms budget is a bug.
- Use `cProfile` on presenter and query code (`uv run python -m cProfile -s cumtime ...`); profile UI-free code first since it is deterministic.
- Add a pytest check for query and presenter speed on a realistic row count (use the 64-upgrade `data.csv` scaled up by factory_boy) so regressions fail the suite.
- Measure on the slowest machine you expect users to have, not only your dev machine.

## Checklist

1. No callback exceeds 50ms; slow work runs in a worker thread or `after` chunks.
2. Workers never touch widgets and never share a SQLite connection with the main thread.
3. Searches are debounced and stale results are discarded.
4. Table loads are a single clear plus a single insert pass, chunked above about 2,000 rows.
5. Heavy imports are lazy, and the window is visible before data loads.
6. Fonts and images are created once, with image references retained.
7. Resize handlers are throttled, and layouts have fixed column widths and reserved status space.
8. Timings are measured and recorded, not assumed.
