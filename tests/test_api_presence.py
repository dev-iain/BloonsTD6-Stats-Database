from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from btd6.api import create_app
from btd6.api.presence import PagePresence

NOW = datetime(2026, 1, 1, 12, 0, 0)


class RecordingPresence(PagePresence):
    def __init__(self, token: str) -> None:
        super().__init__(token)
        self.events: list[tuple[str, str, datetime]] = []

    def heartbeat(self, page_id: str, now: datetime) -> None:
        self.events.append(("heartbeat", page_id, now))
        super().heartbeat(page_id, now)

    def closing(self, page_id: str, now: datetime) -> None:
        self.events.append(("closing", page_id, now))
        super().closing(page_id, now)


class StopSpy:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


@pytest.fixture
def presence() -> RecordingPresence:
    return RecordingPresence("tok")


@pytest.fixture
def spy() -> StopSpy:
    return StopSpy()


def build(tmp_path: Path, presence: PagePresence, spy: StopSpy, **kwargs: Any) -> TestClient:
    app = create_app(
        tmp_path / "missing.db",
        request_stop=spy,
        presence=presence,
        clock=lambda: NOW,
        **kwargs,
    )
    return TestClient(app)


@pytest.mark.parametrize("auto_stop", [False, True])
def test_session_reports_token_and_flag(tmp_path, presence, spy, auto_stop) -> None:
    client = build(tmp_path, presence, spy, auto_stop=auto_stop)
    response = client.get("/api/session")
    assert response.status_code == 200
    assert response.json() == {"token": "tok", "auto_stop": auto_stop, "heartbeat_seconds": 10}


def test_session_default_token_is_stable(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "missing.db", request_stop=StopSpy()))
    first = client.get("/api/session").json()
    second = client.get("/api/session").json()
    assert isinstance(first["token"], str) and first["token"]
    assert first["token"] == second["token"]
    assert first["auto_stop"] is False


@pytest.mark.parametrize("content_type", ["application/json", "text/plain;charset=UTF-8"])
@pytest.mark.parametrize("event", ["heartbeat", "closing"])
def test_presence_valid_event(tmp_path, presence, spy, content_type, event) -> None:
    client = build(tmp_path, presence, spy)
    body = f'{{"token": "tok", "page": "p1", "event": "{event}"}}'
    response = client.post("/api/presence", content=body, headers={"Content-Type": content_type})
    assert response.status_code == 204
    assert response.content == b""
    assert presence.events == [(event, "p1", NOW)]


@pytest.mark.parametrize(
    "body",
    [
        '{"page": "p1", "event": "heartbeat"}',
        '{"token": "nope", "page": "p1", "event": "heartbeat"}',
    ],
)
def test_presence_bad_token_is_forbidden(tmp_path, presence, spy, body) -> None:
    client = build(tmp_path, presence, spy)
    response = client.post("/api/presence", content=body)
    assert response.status_code == 403
    assert response.json() == {"error": "Bad session token"}
    assert presence.events == []


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[1, 2]",
        '"text"',
        '{"token": "tok", "event": "heartbeat"}',
        '{"token": "tok", "page": "", "event": "heartbeat"}',
        '{"token": "tok", "page": "   ", "event": "heartbeat"}',
        '{"token": "tok", "page": "p1", "event": "explode"}',
        '{"token": "tok", "page": "p1"}',
    ],
)
def test_presence_invalid_body_is_422(tmp_path, presence, spy, body) -> None:
    client = build(tmp_path, presence, spy)
    response = client.post("/api/presence", content=body)
    assert response.status_code == 422
    assert "error" in response.json()
    assert presence.events == []


def test_auto_stop_off_never_stops(tmp_path, presence, spy) -> None:
    presence.heartbeat("a", NOW)
    presence.closing("a", NOW)
    with build(tmp_path, presence, spy, auto_stop=False):
        time.sleep(0.3)
    assert spy.calls == 0


def test_auto_stop_on_stops_when_empty(tmp_path, presence, spy) -> None:
    stale = PagePresence("tok")
    stale.heartbeat("a", NOW)
    stale.closing("a", NOW)
    app = create_app(
        tmp_path / "missing.db",
        request_stop=spy,
        presence=stale,
        clock=lambda: datetime(2026, 1, 1, 13, 0, 0),
        auto_stop=True,
        watch_interval=0.01,
    )
    with TestClient(app):
        deadline = time.monotonic() + 1.0
        while spy.calls == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
    assert spy.calls == 1


def test_app_state_exposes_auto_stop(tmp_path: Path) -> None:
    app = create_app(tmp_path / "missing.db", request_stop=StopSpy(), auto_stop=True)
    assert app.state.auto_stop is True
    assert create_app(tmp_path / "missing.db").state.auto_stop is False
