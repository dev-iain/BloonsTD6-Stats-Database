from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
INDEX_HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")
APP_JS = (FRONTEND / "app.js").read_text(encoding="utf-8")


def rank_form_html() -> str:
    start = INDEX_HTML.index('id="rank-form"')
    return INDEX_HTML[start : INDEX_HTML.index("</form>", start)]


def test_rank_form_has_money_input() -> None:
    form = rank_form_html()
    assert 'id="rank-money"' in form
    assert 'name="money"' in form
    assert 'type="number"' in form
    assert 'min="0"' in form


def test_rank_money_input_is_optional() -> None:
    form = rank_form_html()
    money_tag = form[form.index('id="rank-money"') :].split(">", 1)[0]
    assert "required" not in money_tag


def test_rank_form_has_tower_select_defaulting_to_all() -> None:
    form = rank_form_html()
    assert '<select id="rank-tower" name="tower">' in form
    assert '<option value="">All towers</option>' in form


def test_tower_select_is_filled_from_api() -> None:
    assert 'fetch("/api/towers")' in APP_JS
    assert "#rank-tower" in APP_JS or '"rank-tower"' in APP_JS
