from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from btd6.api.presence import (
    GRACE_SECONDS,
    HEARTBEAT_SECONDS,
    IDLE_SECONDS,
    PagePresence,
    watch_presence,
)

START = datetime(2026, 1, 1, 12, 0, 0)


def after(seconds: float) -> datetime:
    return START + timedelta(seconds=seconds)


def test_constants() -> None:
    assert (HEARTBEAT_SECONDS, IDLE_SECONDS, GRACE_SECONDS) == (10, 90, 5)


def test_token_attribute() -> None:
    assert PagePresence("tok").token == "tok"


@pytest.mark.parametrize("seconds", [0, 100, 100000])
def test_never_connected_never_stops(seconds: float) -> None:
    assert PagePresence("tok").should_stop(after(seconds)) is False


def test_closing_unknown_page_is_fine() -> None:
    presence = PagePresence("tok")
    presence.closing("ghost", START)
    assert presence.should_stop(after(100)) is False


@pytest.mark.parametrize(("seconds", "expected"), [(0, False), (4.9, False), (5, True), (60, True)])
def test_single_page_closing_then_grace(seconds: float, expected: bool) -> None:
    presence = PagePresence("tok")
    presence.heartbeat("a", START)
    presence.closing("a", START)
    assert presence.should_stop(after(seconds)) is expected


def test_reload_within_grace_stays_alive() -> None:
    presence = PagePresence("tok")
    presence.heartbeat("a", START)
    presence.closing("a", START)
    presence.heartbeat("b", after(2))
    for seconds in (3, 8, 12, 60):
        presence.heartbeat("b", after(seconds))
        assert presence.should_stop(after(seconds)) is False


def test_two_pages_one_closes() -> None:
    presence = PagePresence("tok")
    presence.heartbeat("a", START)
    presence.heartbeat("b", START)
    presence.closing("a", after(1))
    assert presence.should_stop(after(30)) is False
    assert presence.live_pages(after(30)) == 1


def test_two_pages_both_close() -> None:
    presence = PagePresence("tok")
    presence.heartbeat("a", START)
    presence.heartbeat("b", START)
    presence.closing("a", after(1))
    presence.closing("b", after(2))
    assert presence.should_stop(after(6.9)) is False
    assert presence.should_stop(after(7)) is True


@pytest.mark.parametrize(("seconds", "expected"), [(90, False), (94, False), (95, True)])
def test_crashed_page_expires(seconds: float, expected: bool) -> None:
    presence = PagePresence("tok")
    presence.heartbeat("a", START)
    assert presence.should_stop(after(seconds)) is expected


@pytest.mark.parametrize(("seconds", "expected"), [(0, 1), (90, 1), (90.1, 0)])
def test_live_pages_idle_boundary(seconds: float, expected: int) -> None:
    presence = PagePresence("tok")
    presence.heartbeat("a", START)
    assert presence.live_pages(after(seconds)) == expected


def test_custom_idle_and_grace() -> None:
    presence = PagePresence("tok", idle_seconds=10, grace_seconds=2)
    presence.heartbeat("a", START)
    assert presence.should_stop(after(11.9)) is False
    assert presence.should_stop(after(12)) is True


def test_heartbeat_revives_after_stop() -> None:
    presence = PagePresence("tok")
    presence.heartbeat("a", START)
    presence.closing("a", START)
    assert presence.should_stop(after(10)) is True
    presence.heartbeat("a", after(11))
    assert presence.should_stop(after(11)) is False


def test_repeated_heartbeat_extends_life() -> None:
    presence = PagePresence("tok")
    presence.heartbeat("a", START)
    presence.heartbeat("a", after(80))
    assert presence.live_pages(after(150)) == 1


def test_watch_presence_stops_once_and_returns() -> None:
    presence = PagePresence("tok")
    presence.heartbeat("a", START)
    presence.closing("a", START)
    ticks = iter(range(0, 100))
    calls: list[int] = []

    def clock() -> datetime:
        return after(next(ticks))

    asyncio.run(watch_presence(presence, clock, lambda: calls.append(1), interval=0))
    assert calls == [1]


class ClockExhaustedError(Exception):
    """The scripted clock has no readings left."""


def test_watch_presence_waits_while_live() -> None:
    presence = PagePresence("tok")
    presence.heartbeat("a", START)
    readings = iter([after(1), after(2), after(3)])
    seen: list[datetime] = []

    def clock() -> datetime:
        reading = next(readings, None)
        if reading is None:
            raise ClockExhaustedError
        seen.append(reading)
        return reading

    calls: list[int] = []
    with pytest.raises(ClockExhaustedError):
        asyncio.run(watch_presence(presence, clock, lambda: calls.append(1), interval=0))
    assert calls == [] and len(seen) == 3
