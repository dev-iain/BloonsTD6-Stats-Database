from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
INDEX_HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")
APP_JS = (FRONTEND / "app.js").read_text(encoding="utf-8")


def test_index_has_live_toggle() -> None:
    assert re.search(r'<input[^>]*id="recommend-live"[^>]*type="checkbox"', INDEX_HTML)


def test_index_has_live_status() -> None:
    assert 'id="recommend-live-status"' in INDEX_HTML


def test_app_polls_game_state_endpoint() -> None:
    assert "/api/game-state" in APP_JS


def test_app_polls_every_two_seconds() -> None:
    assert "LIVE_POLL_MS = 2000" in APP_JS


def test_app_shows_no_game_message() -> None:
    assert "No game connected" in APP_JS


def test_app_shows_stale_message() -> None:
    assert "Game state is stale" in APP_JS


def test_app_shows_live_status() -> None:
    assert "Live · round " in APP_JS
    assert "s ago" in APP_JS
