from __future__ import annotations

import pytest

from btd6 import recommend as recommend_module
from btd6.api.params import RecommendOptions, form_to_recommend_options
from btd6.query import QueryError
from btd6.recommend import OwnedTower


def base_form(**overrides: str | None) -> dict[str, str | None]:
    form: dict[str, str | None] = {"round": "63", "money": "5000"}
    form.update(overrides)
    return form


def test_recommend_options_base_form() -> None:
    options = form_to_recommend_options(base_form())

    assert options == RecommendOptions(
        round_number=63,
        money=5000,
        difficulty="medium",
        limit=None,
        horizon=recommend_module.DEFAULT_HORIZON,
    )


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


def test_recommend_options_horizon_defaults_to_default_horizon() -> None:
    assert form_to_recommend_options(base_form()).horizon == recommend_module.DEFAULT_HORIZON


@pytest.mark.parametrize("blank", [None, "", "  "])
def test_recommend_options_blank_horizon_is_default(blank: str | None) -> None:
    assert (
        form_to_recommend_options(base_form(horizon=blank)).horizon
        == recommend_module.DEFAULT_HORIZON
    )


@pytest.mark.parametrize(("text", "expected"), [("1", 1), ("3", 3), (" 7 ", 7)])
def test_recommend_options_horizon_is_parsed(text: str, expected: int) -> None:
    assert form_to_recommend_options(base_form(horizon=text)).horizon == expected


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("abc", "horizon must be a whole number, got 'abc'"),
        ("1.5", "horizon must be a whole number, got '1.5'"),
        ("0", "horizon must be at least 1, got 0"),
        ("-2", "horizon must be at least 1, got -2"),
    ],
)
def test_recommend_options_invalid_horizon_is_rejected(text: str, message: str) -> None:
    with pytest.raises(QueryError) as caught:
        form_to_recommend_options(base_form(horizon=text))

    assert str(caught.value) == message


def test_recommend_options_one_per_tower_and_owned_default_to_off() -> None:
    options = form_to_recommend_options(base_form())

    assert options.one_per_tower is False
    assert list(options.owned) == []


@pytest.mark.parametrize("text", ["true", "TRUE", "True", "1", "on", "On"])
def test_recommend_options_one_per_tower_true_spellings(text: str) -> None:
    assert form_to_recommend_options(base_form(one_per_tower=text)).one_per_tower is True


@pytest.mark.parametrize("text", ["false", "False", "FALSE", "0", None, "", "   "])
def test_recommend_options_one_per_tower_false_spellings(text: str | None) -> None:
    assert form_to_recommend_options(base_form(one_per_tower=text)).one_per_tower is False


@pytest.mark.parametrize("text", ["yes", "2", "maybe", "truee"])
def test_recommend_options_one_per_tower_invalid(text: str) -> None:
    with pytest.raises(QueryError) as caught:
        form_to_recommend_options(base_form(one_per_tower=text))

    assert str(caught.value) == f"one_per_tower must be true or false, got {text!r}"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Ninja Monkey 0-0-0", [OwnedTower("Ninja Monkey", "0-0-0")]),
        (["Ninja Monkey 0-0-0"], [OwnedTower("Ninja Monkey", "0-0-0")]),
        (
            ["Ninja Monkey 0-0-0", "Dart Monkey 2-0-3"],
            [OwnedTower("Ninja Monkey", "0-0-0"), OwnedTower("Dart Monkey", "2-0-3")],
        ),
        ("Bomb Shooter 5-0-5", [OwnedTower("Bomb Shooter", "5-0-5")]),
        ([], []),
        (None, []),
    ],
    ids=["str", "one_item_list", "two_items", "multi_word_name", "empty_list", "none"],
)
def test_recommend_options_owned_values(value: object, expected: list[OwnedTower]) -> None:
    options = form_to_recommend_options({**base_form(), "owned": value})

    assert list(options.owned) == expected


@pytest.mark.parametrize(
    "text", ["Ninja", "Ninja Monkey", "0-0-0", "Ninja Monkey 1-2", "Ninja Monkey abc", ""]
)
def test_recommend_options_owned_without_trailing_path(text: str) -> None:
    with pytest.raises(QueryError) as caught:
        form_to_recommend_options({**base_form(), "owned": [text]})

    assert str(caught.value) == f"owned must be '<tower name> X-Y-Z', got {text!r}"


def test_recommend_options_owned_second_item_invalid() -> None:
    with pytest.raises(QueryError, match="got 'Ninja'"):
        form_to_recommend_options({**base_form(), "owned": ["Dart Monkey 0-0-0", "Ninja"]})
