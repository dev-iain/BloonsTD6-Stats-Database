from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta

HEARTBEAT_SECONDS = 10
IDLE_SECONDS = 90
GRACE_SECONDS = 5


class PagePresence:
    def __init__(
        self,
        token: str,
        idle_seconds: float = IDLE_SECONDS,
        grace_seconds: float = GRACE_SECONDS,
    ) -> None:
        self.token = token
        self.idle = timedelta(seconds=idle_seconds)
        self.grace = timedelta(seconds=grace_seconds)
        self.last_beats: dict[str, datetime] = {}
        self.last_emptied: datetime | None = None
        self.ever_connected = False

    def heartbeat(self, page_id: str, now: datetime) -> None:
        self.last_beats[page_id] = now
        self.ever_connected = True

    def closing(self, page_id: str, now: datetime) -> None:
        if self.last_beats.pop(page_id, None) is None:
            return
        if not self.last_beats:
            self.last_emptied = now

    def live_pages(self, now: datetime) -> int:
        return sum(1 for beat in self.last_beats.values() if now - beat <= self.idle)

    def should_stop(self, now: datetime) -> bool:
        if not self.ever_connected or self.live_pages(now) > 0:
            return False
        empty_since = [beat + self.idle for beat in self.last_beats.values()]
        if self.last_emptied is not None:
            empty_since.append(self.last_emptied)
        return now - max(empty_since) >= self.grace


async def watch_presence(
    presence: PagePresence,
    clock: Callable[[], datetime],
    request_stop: Callable[[], None],
    interval: float = 1.0,
) -> None:
    while True:
        await asyncio.sleep(interval)
        if presence.should_stop(clock()):
            request_stop()
            return
