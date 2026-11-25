from __future__ import annotations

import os
import signal
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import requests

from btd6 import launcher


@pytest.fixture
def listening_port() -> Iterator[int]:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    try:
        yield server.getsockname()[1]
    finally:
        server.close()


@pytest.fixture
def closed_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "http://127.0.0.1:8000"),
        ("0.0.0.0", "http://127.0.0.1:8000"),
        ("::", "http://127.0.0.1:8000"),
        ("", "http://127.0.0.1:8000"),
        ("localhost", "http://localhost:8000"),
    ],
)
def test_browser_url(host, expected):
    assert launcher.browser_url(host, 8000) == expected


@pytest.mark.parametrize(
    ("platform", "command"),
    [("darwin", ["open", "steam://x"]), ("linux", ["xdg-open", "steam://x"])],
)
def test_open_uri_uses_platform_opener(monkeypatch, platform, command):
    commands: list[list[str]] = []
    monkeypatch.setattr(launcher.sys, "platform", platform)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda args, **kwargs: commands.append(args))

    launcher.open_uri("steam://x")

    assert commands == [command]


def test_open_uri_on_windows_uses_startfile(monkeypatch):
    started: list[str] = []
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.setattr(launcher.os, "startfile", started.append, raising=False)

    launcher.open_uri("steam://x")

    assert started == ["steam://x"]


def test_wait_for_port_open(listening_port):
    assert launcher.wait_for_port("127.0.0.1", listening_port, timeout=2.0) is True


def test_wait_for_port_times_out(closed_port):
    assert launcher.wait_for_port("127.0.0.1", closed_port, timeout=0.3) is False


def test_wait_for_port_maps_wildcard_host(listening_port):
    assert launcher.wait_for_port("0.0.0.0", listening_port, timeout=2.0) is True


def test_open_browser_when_ready_opens_url(monkeypatch, listening_port):
    opened: list[str] = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)

    thread = launcher.open_browser_when_ready("http://x", "127.0.0.1", listening_port)
    thread.join(timeout=5)

    assert opened == ["http://x"]


def test_open_browser_when_ready_skips_when_never_listening(monkeypatch, closed_port):
    opened: list[str] = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    monkeypatch.setattr(launcher, "READY_TIMEOUT_SECONDS", 0.3)

    thread = launcher.open_browser_when_ready("http://x", "127.0.0.1", closed_port)
    thread.join(timeout=5)

    assert opened == []


class FakeResponse:
    def __init__(self, payload: Any = None, broken_json: bool = False) -> None:
        self.payload = payload
        self.broken_json = broken_json

    def json(self) -> Any:
        if self.broken_json:
            raise ValueError("not json")
        return self.payload


def stub_health(monkeypatch: pytest.MonkeyPatch, response: FakeResponse | Exception) -> list[str]:
    urls: list[str] = []

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        urls.append(url)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    return urls


def test_stop_timeout_is_ten_seconds() -> None:
    assert launcher.STOP_TIMEOUT_SECONDS == 10


def test_port_in_use_listening(listening_port) -> None:
    assert launcher.port_in_use("127.0.0.1", listening_port) is True


def test_port_in_use_free(closed_port) -> None:
    assert launcher.port_in_use("127.0.0.1", closed_port) is False


def test_port_in_use_maps_wildcard_host(listening_port) -> None:
    assert launcher.port_in_use("0.0.0.0", listening_port) is True


def test_wait_for_port_free_already_free(closed_port) -> None:
    assert launcher.wait_for_port_free("127.0.0.1", closed_port, timeout=1.0) is True


def test_wait_for_port_free_times_out(listening_port) -> None:
    started = time.monotonic()
    assert launcher.wait_for_port_free("127.0.0.1", listening_port, timeout=0.3) is False
    assert time.monotonic() - started < 3.0


def test_wait_for_port_free_when_released_midway() -> None:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]
    threading.Timer(0.2, server.close).start()

    assert launcher.wait_for_port_free("127.0.0.1", port, timeout=5.0) is True


def test_running_advisor_pid_valid_reply(monkeypatch) -> None:
    urls = stub_health(monkeypatch, FakeResponse({"app": "btd6", "pid": 4321}))

    assert launcher.running_advisor_pid("127.0.0.1", 8123) == 4321
    assert urls == ["http://127.0.0.1:8123/api/health"]


def test_running_advisor_pid_maps_wildcard_host(monkeypatch) -> None:
    urls = stub_health(monkeypatch, FakeResponse({"app": "btd6", "pid": 7}))

    assert launcher.running_advisor_pid("0.0.0.0", 8123) == 7
    assert urls == ["http://127.0.0.1:8123/api/health"]


@pytest.mark.parametrize(
    "response",
    [
        requests.ConnectionError("refused"),
        requests.Timeout("slow"),
        FakeResponse(broken_json=True),
        FakeResponse({"app": "other", "pid": 4321}),
        FakeResponse({"pid": 4321}),
        FakeResponse({"app": "btd6", "pid": "4321"}),
        FakeResponse({"app": "btd6"}),
        FakeResponse(["btd6", 4321]),
        FakeResponse(None),
    ],
    ids=[
        "connection_error",
        "timeout",
        "non_json",
        "other_app",
        "missing_app",
        "pid_string",
        "missing_pid",
        "json_list",
        "json_null",
    ],
)
def test_running_advisor_pid_not_an_advisor(monkeypatch, response) -> None:
    stub_health(monkeypatch, response)

    assert launcher.running_advisor_pid("127.0.0.1", 8123) is None


def test_running_advisor_pid_uses_two_second_timeout(monkeypatch) -> None:
    seen: list[Any] = []

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        seen.append(kwargs.get("timeout"))
        return FakeResponse({"app": "btd6", "pid": 1})

    monkeypatch.setattr(requests, "get", fake_get)
    launcher.running_advisor_pid("127.0.0.1", 8123)

    assert seen == [2]


def test_stop_process_sends_sigterm(monkeypatch) -> None:
    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(launcher.sys, "platform", "linux")
    monkeypatch.setattr(launcher.os, "kill", lambda pid, sig: kills.append((pid, sig)))

    launcher.stop_process(os.getpid() + 1)

    assert kills == [(os.getpid() + 1, signal.SIGTERM)]


def test_stop_process_ignores_own_pid(monkeypatch) -> None:
    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(launcher.os, "kill", lambda pid, sig: kills.append((pid, sig)))

    launcher.stop_process(os.getpid())

    assert kills == []


def test_stop_process_already_exited_counts_as_stopped(monkeypatch) -> None:
    def gone(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(launcher.sys, "platform", "linux")
    monkeypatch.setattr(launcher.os, "kill", gone)

    assert launcher.stop_process(os.getpid() + 1) is None


class AdvisorScenario:
    def __init__(self, in_use: bool, pid: int | None, freed: bool) -> None:
        self.in_use = in_use
        self.pid = pid
        self.freed = freed
        self.stopped: list[int] = []
        self.waits: list[tuple[str, int, float]] = []


@pytest.fixture
def scenario(monkeypatch: pytest.MonkeyPatch):
    def install(in_use: bool, pid: int | None, freed: bool) -> AdvisorScenario:
        state = AdvisorScenario(in_use, pid, freed)

        def fake_wait(host: str, port: int, timeout: float) -> bool:
            state.waits.append((host, port, timeout))
            return state.freed

        monkeypatch.setattr(launcher, "port_in_use", lambda host, port: state.in_use)
        monkeypatch.setattr(launcher, "running_advisor_pid", lambda host, port: state.pid)
        monkeypatch.setattr(launcher, "stop_process", state.stopped.append)
        monkeypatch.setattr(launcher, "wait_for_port_free", fake_wait)
        return state

    return install


def test_replace_running_advisor_port_free(scenario, capsys) -> None:
    state = scenario(in_use=False, pid=None, freed=True)

    assert launcher.replace_running_advisor("127.0.0.1", 8000) is None
    assert state.stopped == []
    assert state.waits == []
    assert capsys.readouterr().out == ""


def test_replace_running_advisor_stops_old_advisor(scenario, capsys) -> None:
    state = scenario(in_use=True, pid=4321, freed=True)

    assert launcher.replace_running_advisor("127.0.0.1", 8000) is None
    assert state.stopped == [4321]
    assert state.waits == [("127.0.0.1", 8000, launcher.STOP_TIMEOUT_SECONDS)]
    assert "Stopping the advisor that is already running (pid 4321)..." in capsys.readouterr().out


def test_replace_running_advisor_will_not_stop(scenario) -> None:
    state = scenario(in_use=True, pid=4321, freed=False)

    message = launcher.replace_running_advisor("127.0.0.1", 8000)

    assert state.stopped == [4321]
    assert message == (
        "Could not stop the advisor on port 8000 (pid 4321). "
        "Close its window and run the start script again."
    )


def test_replace_running_advisor_port_held_by_other_program(scenario) -> None:
    state = scenario(in_use=True, pid=None, freed=True)

    message = launcher.replace_running_advisor("127.0.0.1", 9100)

    assert state.stopped == []
    assert message == (
        "Port 9100 is already in use. If an older BTD6 advisor is running, close its window "
        "(or press Ctrl+C in it) and run the start script again; otherwise use --port N."
    )
