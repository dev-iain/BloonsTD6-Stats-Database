from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
INDEX_HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")
APP_JS = (FRONTEND / "app.js").read_text(encoding="utf-8")


def test_index_has_recommend_tab_button() -> None:
    assert 'data-tab="recommend"' in INDEX_HTML
    assert ">Recommend</button>" in INDEX_HTML


def test_recommend_tab_follows_rounds_tab() -> None:
    assert INDEX_HTML.index('data-tab="rounds"') < INDEX_HTML.index('data-tab="recommend"')


@pytest.mark.parametrize(
    "element_id",
    [
        "tab-recommend",
        "recommend-form",
        "recommend-round",
        "recommend-money",
        "recommend-difficulty",
        "recommend-limit",
        "recommend-status",
        "recommend-threats",
        "recommend-table",
    ],
)
def test_index_has_recommend_element(element_id: str) -> None:
    assert f'id="{element_id}"' in INDEX_HTML


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard", "impoppable"])
def test_difficulty_select_offers_each_difficulty(difficulty: str) -> None:
    assert f'<option value="{difficulty}"' in INDEX_HTML


def test_medium_is_the_default_difficulty() -> None:
    assert '<option value="medium" selected>' in INDEX_HTML


def test_app_requests_recommendations_endpoint() -> None:
    assert "/api/recommendations" in APP_JS


def test_app_shows_empty_message() -> None:
    assert "No affordable upgrade can handle this round." in APP_JS


def test_app_never_uses_inner_html() -> None:
    assert "innerHTML" not in APP_JS
