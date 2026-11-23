from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class Scheduler(Protocol):
    """The slice of Tk's `after` API that debounce and polling need."""

    def after(self, delay_ms: int, callback: Callable[[], None]) -> str: ...

    def after_cancel(self, token: str) -> None: ...
