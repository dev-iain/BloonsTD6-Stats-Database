from __future__ import annotations

import re
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
        "recommend-horizon",
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


def test_horizon_input_defaults_to_five_rounds() -> None:
    assert (
        '<input id="recommend-horizon" name="horizon" type="number" min="1" step="1" value="5">'
        in INDEX_HTML
    )


def test_recommend_table_shows_first_leak_round() -> None:
    assert '{ key: "first_leak_round", label: "Leaks at", numeric: true }' in APP_JS


def input_tag(element_id: str) -> str:
    match = re.search(rf"<input\b[^>]*\bid=\"{element_id}\"[^>]*>", INDEX_HTML)
    assert match, element_id
    return match.group(0)


def test_one_per_tower_checkbox_is_in_the_recommend_form() -> None:
    checkbox_tag = input_tag("recommend-one-per-tower")

    assert 'type="checkbox"' in checkbox_tag
    assert 'name="one_per_tower"' in checkbox_tag
    assert 'value="true"' in checkbox_tag
    assert "checked" not in checkbox_tag
    form_start = INDEX_HTML.index('id="recommend-form"')
    assert form_start < INDEX_HTML.index('id="recommend-one-per-tower"')


def test_one_per_tower_checkbox_has_a_label() -> None:
    assert "One per tower" in INDEX_HTML


def test_recommend_table_shows_upgrade_from() -> None:
    block = APP_JS[APP_JS.index("const RECOMMEND_COLUMNS") :]
    block = block[: block.index("];")]

    assert '{ key: "upgrade_from", label: "Upgrade from" }' in block
    assert block.index('key: "path"') < block.index('key: "upgrade_from"')
    assert block.index('key: "upgrade_from"') < block.index('key: "total_cost"')


def test_app_sends_owned_towers_as_repeated_params() -> None:
    assert 'append("owned"' in APP_JS


def test_app_reports_how_many_owned_towers_are_counted() -> None:
    assert "Counting " in APP_JS
    assert "owned towers" in APP_JS


def test_one_per_tower_toggle_resubmits() -> None:
    assert 'getElementById("recommend-one-per-tower")' in APP_JS
    assert "attachOnePerTowerToggle();" in APP_JS
