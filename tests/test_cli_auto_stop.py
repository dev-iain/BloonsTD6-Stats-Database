from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import uvicorn

from btd6 import launcher
from btd6.cli import main


@pytest.fixture
def served_apps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[Any]:
    monkeypatch.setattr("btd6.cli.KEY_FILE_PATH", tmp_path / "gemini_api_key.txt", raising=False)
    apps: list[Any] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: apps.append(app))
    monkeypatch.setattr(launcher, "replace_running_advisor", lambda host, port: None)
    monkeypatch.setattr(launcher, "open_browser_when_ready", lambda url, host, port: None)
    return apps


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "btd6.db"
    path.touch()
    return path


def test_start_enables_auto_stop(database, served_apps) -> None:
    main(["--db", str(database), "start"])
    assert served_apps[0].state.auto_stop is True


def test_start_no_browser_disables_auto_stop(database, served_apps) -> None:
    main(["--db", str(database), "start", "--no-browser"])
    assert served_apps[0].state.auto_stop is False


def test_serve_never_auto_stops(database, served_apps) -> None:
    main(["--db", str(database), "serve"])
    assert served_apps[0].state.auto_stop is False
