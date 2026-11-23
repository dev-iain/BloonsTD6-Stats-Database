from __future__ import annotations

from collections.abc import Callable

from btd6.ui.presenters import FilterInputs
from btd6.ui.worker import BackgroundRunner


class FakeScheduler:
    def __init__(self) -> None:
        self.pending: dict[str, tuple[int, Callable[[], None]]] = {}
        self.cancelled: list[str] = []
        self._counter = 0

    def after(self, delay_ms: int, callback: Callable[[], None]) -> str:
        self._counter += 1
        token = f"after#{self._counter}"
        self.pending[token] = (delay_ms, callback)
        return token

    def after_cancel(self, token: str) -> None:
        self.cancelled.append(token)
        self.pending.pop(token, None)

    def fire_all(self) -> None:
        for token in list(self.pending):
            _, callback = self.pending.pop(token)
            callback()


class DeferredThreads:
    """Collects thread bodies so a test decides when each 'thread' runs."""

    def __init__(self) -> None:
        self.targets: list[Callable[[], None]] = []

    def start(self, target: Callable[[], None]) -> None:
        self.targets.append(target)

    def run_next(self) -> None:
        self.targets.pop(0)()

    def run_all(self) -> None:
        while self.targets:
            self.run_next()


class FakeView:
    def __init__(self) -> None:
        self.rows: list[tuple[str, ...]] | None = None
        self.placeholder: tuple[str, bool] | None = None
        self.statuses: list[tuple[str, bool]] = []
        self.busy_states: list[bool] = []
        self.errors: dict[str, str] = {}
        self.sort: tuple[str | None, bool] | None = None
        self.filters_shown: FilterInputs | None = None

    def show_rows(self, rows: list[tuple[str, ...]]) -> None:
        self.rows = rows

    def show_placeholder(self, message: str, offer_load: bool) -> None:
        self.placeholder = (message, offer_load)

    def show_status(self, message: str, is_error: bool) -> None:
        self.statuses.append((message, is_error))

    def set_busy(self, busy: bool) -> None:
        self.busy_states.append(busy)

    def show_field_errors(self, errors: dict[str, str]) -> None:
        self.errors = errors

    def show_sort(self, column: str | None, descending: bool) -> None:
        self.sort = (column, descending)

    def show_filters(self, inputs: FilterInputs) -> None:
        self.filters_shown = inputs

    @property
    def last_status(self) -> tuple[str, bool]:
        return self.statuses[-1]


def make_runner(scheduler: FakeScheduler, threads: DeferredThreads) -> BackgroundRunner:
    return BackgroundRunner(scheduler, start_thread=threads.start)
