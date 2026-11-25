from __future__ import annotations

import copy
import re
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.etl.extract import extract_row, path_from_code
from btd6.etl.fetch import CODE_PATTERN, deep_merge

EXPECTED_ROW_KEYS = {
    "path",
    "range",
    "footprint_radius",
    "attack_rate",
    "projectile_count",
    "projectile_damage",
    "projectile_pierce",
    "projectile_speed",
    "projectile_radius",
    "projectile_lifespan",
    "can_hit_camo",
    "ability_cooldown",
    "damage_type",
    "can_pop_lead",
    "can_pop_black",
    "can_pop_white",
    "can_pop_purple",
    "can_pop_glass",
    "can_pop_frozen",
}
SHORT_TEXT = st.text(max_size=5)
JSON_LEAVES = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    SHORT_TEXT,
)
CODE_KEYS = st.from_regex(r"_\d{3}", fullmatch=True)
DICT_KEYS = st.one_of(SHORT_TEXT, CODE_KEYS)
JSON_VALUES = st.recursive(
    JSON_LEAVES,
    lambda children: st.dictionaries(DICT_KEYS, children, max_size=4),
    max_leaves=15,
)
JSON_DICTS = st.dictionaries(DICT_KEYS, JSON_VALUES, max_size=5)

OPTIONAL_NUMBER = st.one_of(st.integers(0, 500), st.floats(0, 500, allow_nan=False))


def maybe_present(fields: dict[str, st.SearchStrategy[Any]]) -> st.SearchStrategy[dict[str, Any]]:
    return st.fixed_dictionaries({}, optional=fields)


def ordered_container(entry: st.SearchStrategy[dict[str, Any]]) -> st.SearchStrategy[dict]:
    def build(entries: dict[str, dict[str, Any]], drop_order: bool) -> dict[str, Any]:
        container: dict[str, Any] = dict(entries)
        if not drop_order:
            container["_order"] = list(entries)
        return container

    names = st.text("abc", min_size=1, max_size=2)
    return st.builds(build, st.dictionaries(names, entry, max_size=2), st.booleans())


PROJECTILES = maybe_present(
    {
        "count": OPTIONAL_NUMBER,
        "damage": OPTIONAL_NUMBER,
        "pierce": OPTIONAL_NUMBER,
        "speed": OPTIONAL_NUMBER,
        "radius": OPTIONAL_NUMBER,
        "lifespan": OPTIONAL_NUMBER,
        "immuneBloonProperties": st.sampled_from([0, 1, 2, 4, 5, 8, 12, 17, 64, 72, 73, 99]),
        "filterInvisible": st.booleans(),
    }
)
ATTACKS = maybe_present({"rate": OPTIONAL_NUMBER, "projectiles": ordered_container(PROJECTILES)})
ABILITIES = maybe_present({"cooldown": OPTIONAL_NUMBER})
STATS = maybe_present(
    {
        "range": OPTIONAL_NUMBER,
        "footprintRadius": OPTIONAL_NUMBER,
        "attacks": ordered_container(ATTACKS),
        "abilities": ordered_container(ABILITIES),
    }
)


@settings(max_examples=100, deadline=None)
@given(base=JSON_DICTS)
def test_merging_empty_override_returns_base(base: dict[str, Any]) -> None:
    assert deep_merge(base, {}) == base


@settings(max_examples=100, deadline=None)
@given(base=JSON_DICTS, override=JSON_DICTS)
def test_deep_merge_never_mutates_base(base: dict[str, Any], override: dict[str, Any]) -> None:
    snapshot = copy.deepcopy(base)
    deep_merge(base, override)
    assert base == snapshot


@settings(max_examples=100, deadline=None)
@given(base=JSON_DICTS, override=JSON_DICTS)
def test_non_crosspath_override_keys_appear_in_result(
    base: dict[str, Any], override: dict[str, Any]
) -> None:
    result = deep_merge(base, override)
    for key in override:
        if not CODE_PATTERN.match(key):
            assert key in result


ORDER_LISTS = st.lists(st.text("abcd", min_size=1, max_size=2), max_size=5, unique=True)


@settings(max_examples=100, deadline=None)
@given(base_order=ORDER_LISTS, override_order=ORDER_LISTS)
def test_order_merge_keeps_base_entries_in_order(
    base_order: list[str], override_order: list[str]
) -> None:
    result = deep_merge({"_order": base_order}, {"_order": override_order})["_order"]
    assert result[: len(base_order)] == base_order
    assert len(result) == len(set(result))
    assert set(result) == set(base_order) | set(override_order)


@settings(max_examples=100, deadline=None)
@given(base_order=ORDER_LISTS, override_order=ORDER_LISTS)
def test_order_merge_never_mutates_inputs(base_order: list[str], override_order: list[str]) -> None:
    base = {"_order": base_order}
    override = {"_order": override_order}
    base_snapshot = copy.deepcopy(base)
    override_snapshot = copy.deepcopy(override)
    deep_merge(base, override)["_order"].append("mutated")
    assert base == base_snapshot
    assert override == override_snapshot


@settings(max_examples=100, deadline=None)
@given(code=CODE_KEYS, stats=STATS)
def test_extract_row_never_raises_and_has_fixed_keys(code: str, stats: dict[str, Any]) -> None:
    row = extract_row(code, stats)
    assert set(row) == EXPECTED_ROW_KEYS
    assert len(row) == 19


@settings(max_examples=100, deadline=None)
@given(digits=st.from_regex(r"\d{3}", fullmatch=True))
def test_path_from_code_matches_path_format(digits: str) -> None:
    assert re.fullmatch(r"\d-\d-\d", path_from_code(f"_{digits}"))
