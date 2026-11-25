from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
INDEX_HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")
APP_JS = (FRONTEND / "app.js").read_text(encoding="utf-8")


def test_quit_button_is_inside_topbar() -> None:
    topbar_start = INDEX_HTML.index('<header class="topbar">')
    button_at = INDEX_HTML.index('id="quit-button"')
    assert topbar_start < button_at < INDEX_HTML.index("</header>")


@pytest.mark.parametrize(
    "snippet",
    [
        '"/api/shutdown"',
        '"X-BTD6-Action": "quit"',
        'method: "POST"',
        "The advisor has stopped. You can close this tab.",
        "attachQuit();",
    ],
)
def test_app_contains_quit_snippet(snippet: str) -> None:
    assert snippet in APP_JS


def test_app_never_uses_inner_html() -> None:
    assert "innerHTML" not in APP_JS


@pytest.mark.parametrize(
    "snippet",
    ['"/api/session"', '"/api/presence"', "sendBeacon", "pagehide", "attachPresence();"],
)
def test_app_contains_presence_snippet(snippet: str) -> None:
    assert snippet in APP_JS
