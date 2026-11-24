from __future__ import annotations

import pytest

from btd6.api.params import RecommendOptions, form_to_recommend_options
from btd6.query import QueryError


def base_form(**overrides: str | None) -> dict[str, str | None]:
    form: dict[str, str | None] = {"round": "63", "money": "5000"}
    form.update(overrides)
    return form


def test_recommend_options_base_form() -> None:
    options = form_to_recommend_options(base_form())

    assert options == RecommendOptions(round_number=63, money=5000, difficulty="medium", limit=None)


def test_recommend_options_all_fields() -> None:
    options = form_to_recommend_options(base_form(difficulty="hard", limit="3"))

    assert (options.difficulty, options.limit) == ("hard", 3)


@pytest.mark.parametrize("field", ["round", "money"])
@pytest.mark.parametrize("blank", ["absent", None, "", "   "])
def test_recommend_options_required_field_missing(field: str, blank: str | None) -> None:
    form = base_form()
    if blank == "absent":
        del form[field]
    else:
        form[field] = blank

    with pytest.raises(QueryError, match=f"^{field} is required$"):
        form_to_recommend_options(form)


def test_recommend_options_whitespace_padded_number_is_accepted() -> None:
    options = form_to_recommend_options(base_form(round=" 63 ", money=" 5000 "))

    assert (options.round_number, options.money) == (63, 5000)


@pytest.mark.parametrize("field", ["round", "money"])
@pytest.mark.parametrize("text", ["abc", "1.5"])
def test_recommend_options_non_integer_is_rejected(field: str, text: str) -> None:
    with pytest.raises(QueryError) as caught:
        form_to_recommend_options(base_form(**{field: text}))

    assert str(caught.value) == f"{field} must be a whole number, got '{text}'"


def test_recommend_options_negative_money_is_rejected() -> None:
    with pytest.raises(QueryError) as caught:
        form_to_recommend_options(base_form(money="-1"))

    assert str(caught.value) == "money must be 0 or more, got -1"


def test_recommend_options_zero_money_is_accepted() -> None:
    assert form_to_recommend_options(base_form(money="0")).money == 0


@pytest.mark.parametrize("blank", [None, "", "  "])
def test_recommend_options_blank_limit_is_none(blank: str | None) -> None:
    assert form_to_recommend_options(base_form(limit=blank)).limit is None


def test_recommend_options_zero_limit_is_rejected() -> None:
    with pytest.raises(QueryError) as caught:
        form_to_recommend_options(base_form(limit="0"))

    assert str(caught.value) == "limit must be at least 1, got 0"


@pytest.mark.parametrize("blank", [None, ""])
def test_recommend_options_difficulty_defaults_to_medium(blank: str | None) -> None:
    assert form_to_recommend_options(base_form(difficulty=blank)).difficulty == "medium"
