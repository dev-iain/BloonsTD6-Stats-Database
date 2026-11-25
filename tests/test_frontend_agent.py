from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
INDEX_HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")
APP_JS = (FRONTEND / "app.js").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "element_id",
    ["agent-ask", "agent-status", "agent-detail", "agent-answer", "agent-table", "agent-tools"],
)
def test_index_has_agent_element(element_id: str) -> None:
    assert f'id="{element_id}"' in INDEX_HTML


def test_agent_section_is_inside_recommend_tab() -> None:
    recommend_start = INDEX_HTML.index('id="tab-recommend"')
    assert recommend_start < INDEX_HTML.index('id="agent-ask"') < INDEX_HTML.index("</main>")


def test_agent_hint_names_key_file() -> None:
    assert "gemini_api_key.txt" in INDEX_HTML


def test_app_requests_agent_endpoint() -> None:
    assert "/api/agent?" in APP_JS


def test_app_attaches_agent_handler() -> None:
    assert "attachAgent();" in APP_JS


def test_app_sends_live_flag_to_agent() -> None:
    assert 'params.set("live", "true")' in APP_JS
