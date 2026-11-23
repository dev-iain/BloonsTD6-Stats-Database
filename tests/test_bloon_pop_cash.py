from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6.etl.pop_cash import bloon_pop_cash

CHILDREN = {
    "Red": [],
    "Blue": [("Red", 1)],
    "Green": [("Blue", 1)],
    "Yellow": [("Green", 1)],
    "Pink": [("Yellow", 1)],
    "Black": [("Pink", 2)],
    "White": [("Pink", 2)],
    "Lead": [("Black", 2)],
    "Zebra": [("Black", 1), ("White", 1)],
    "Rainbow": [("Zebra", 2)],
    "Ceramic": [("Rainbow", 2)],
    "MOAB": [("Ceramic", 4)],
    "BFB": [("MOAB", 4)],
    "ZOMG": [("BFB", 4)],
    "DDT": [("Ceramic", 4)],
    "BAD": [("ZOMG", 2), ("DDT", 3)],
}
MOAB_NAMES = frozenset({"MOAB", "BFB", "ZOMG", "DDT", "BAD"})
KNOWN = {
    "Red": (1, 1),
    "Black": (11, 6),
    "Lead": (23, 7),
    "Zebra": (23, 7),
    "Rainbow": (47, 8),
    "Ceramic": (95, 95),
    "MOAB": (381, 381),
    "DDT": (381, 381),
    "BFB": (1525, 1525),
    "ZOMG": (6101, 6101),
    "BAD": (13346, 13346),
}


def pop_cash(name: str, super_ceramic: bool) -> int:
    return bloon_pop_cash(name, CHILDREN, MOAB_NAMES, super_ceramic)


def test_bloon_pop_cash_base() -> None:
    assert pop_cash("Lead", False) == 23


def test_bloon_pop_cash_leaf() -> None:
    assert pop_cash("Red", False) == 1


def test_bloon_pop_cash_several_children() -> None:
    assert pop_cash("Zebra", False) == 23


def test_bloon_pop_cash_ceramic() -> None:
    assert pop_cash("Ceramic", False) == 95


def test_bloon_pop_cash_moab() -> None:
    assert pop_cash("MOAB", False) == 381


def test_bloon_pop_cash_bad() -> None:
    assert pop_cash("BAD", False) == 13346


def test_bloon_pop_cash_super_first_child_only() -> None:
    assert pop_cash("Lead", True) == 7


@pytest.mark.parametrize(("name", "expected"), KNOWN.items())
@pytest.mark.parametrize("super_ceramic", [False, True])
def test_bloon_pop_cash_known_values(name, expected, super_ceramic) -> None:
    assert pop_cash(name, super_ceramic) == expected[int(super_ceramic)]


@pytest.mark.parametrize("super_ceramic", [False, True])
def test_bloon_pop_cash_missing_name_is_leaf(super_ceramic) -> None:
    assert bloon_pop_cash("Unknown", CHILDREN, MOAB_NAMES, super_ceramic) == 1


def test_bloon_pop_cash_missing_child_is_leaf() -> None:
    assert bloon_pop_cash("Lead", {"Lead": [("Black", 2)]}, frozenset(), False) == 3


@st.composite
def acyclic_children(draw):
    names = [f"B{index}" for index in range(draw(st.integers(1, 6)))]
    children = {}
    for index, name in enumerate(names):
        below = names[:index]
        pair = st.tuples(st.sampled_from(below), st.integers(1, 4)) if below else None
        children[name] = draw(st.lists(pair, max_size=3)) if pair else []
    return children


@given(children=acyclic_children(), super_ceramic=st.booleans())
def test_bloon_pop_cash_at_least_one(children, super_ceramic) -> None:
    for name in children:
        assert bloon_pop_cash(name, children, frozenset(), super_ceramic) >= 1


@given(children=acyclic_children())
def test_bloon_pop_cash_recurrence(children) -> None:
    for name, kids in children.items():
        expected = 1 + sum(
            count * bloon_pop_cash(child_name, children, frozenset(), False)
            for child_name, count in kids
        )
        assert bloon_pop_cash(name, children, frozenset(), False) == expected


@given(children=acyclic_children())
def test_bloon_pop_cash_super_not_above_normal_without_ceramic(children) -> None:
    for name in children:
        normal = bloon_pop_cash(name, children, frozenset(), False)
        assert bloon_pop_cash(name, children, frozenset(), True) <= normal
