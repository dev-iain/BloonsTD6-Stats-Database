from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

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
