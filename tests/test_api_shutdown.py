from __future__ import annotations

import signal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from btd6.api import app as app_module
from btd6.api import create_app

FORBIDDEN_BODY = {"error": "Missing X-BTD6-Action: quit header"}


class StopSpy:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1


@pytest.fixture
def spy() -> StopSpy:
    return StopSpy()


@pytest.fixture
def client(tmp_path: Path, spy: StopSpy) -> TestClient:
    return TestClient(create_app(tmp_path / "missing.db", request_stop=spy))


def test_shutdown_with_header_stops_once(client: TestClient, spy: StopSpy) -> None:
    response = client.post("/api/shutdown", headers={"X-BTD6-Action": "quit"})
    assert response.status_code == 200
    assert response.json() == {"stopping": True}
    assert spy.calls == 1


def test_shutdown_without_header_is_forbidden(client: TestClient, spy: StopSpy) -> None:
    response = client.post("/api/shutdown")
    assert response.status_code == 403
    assert response.json() == FORBIDDEN_BODY
    assert spy.calls == 0


def test_shutdown_wrong_header_is_forbidden(client: TestClient, spy: StopSpy) -> None:
    response = client.post("/api/shutdown", headers={"X-BTD6-Action": "stop"})
    assert response.status_code == 403
    assert response.json() == FORBIDDEN_BODY
    assert spy.calls == 0


def test_shutdown_get_is_not_allowed(client: TestClient, spy: StopSpy) -> None:
    response = client.get("/api/shutdown", headers={"X-BTD6-Action": "quit"})
    assert response.status_code == 405
    assert spy.calls == 0


def test_stop_server_raises_sigint(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[int] = []
    monkeypatch.setattr(app_module.signal, "raise_signal", received.append)
    app_module.stop_server()
    assert received == [signal.SIGINT]


def test_create_app_default_stop_is_stop_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    received: list[int] = []
    monkeypatch.setattr(app_module.signal, "raise_signal", received.append)
    client = TestClient(create_app(tmp_path / "missing.db"))
    response = client.post("/api/shutdown", headers={"X-BTD6-Action": "quit"})
    assert response.status_code == 200
    assert received == [signal.SIGINT]
