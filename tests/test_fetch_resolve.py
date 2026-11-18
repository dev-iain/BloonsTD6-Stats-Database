from __future__ import annotations

import copy
from typing import Any

import pytest

from btd6.etl.fetch import CODE_PATTERN, deep_merge, resolve_all_codes

BASE_RESOLVE_INPUT = {
    "_100": {
        "range": 60,
        "attacks": {"rate": 1, "count": 3},
        "_110": {"range": 70},
    }
}
BASE_RESOLVE_OUTPUT = {
    "_100": {"range": 60, "attacks": {"rate": 1, "count": 3}},
    "_110": {"range": 70, "attacks": {"rate": 1, "count": 3}},
}

DEEP_MERGE_CASES = [
    pytest.param(
        {"attacks": {"rate": 1.0, "count": 1}},
        {"attacks": {"rate": 0.5}},
        {"attacks": {"rate": 0.5, "count": 1}},
        id="test_deep_merge_both_dicts",
    ),
    pytest.param(
        {"attacks": {"rate": 1.0, "count": 1}},
        {"attacks": 0},
        {"attacks": 0},
        id="test_deep_merge_scalar_replaces_dict",
    ),
    pytest.param(
        {},
        {"attacks": {"rate": 0.5}},
        {"attacks": {"rate": 0.5}},
        id="test_deep_merge_key_absent_in_base",
    ),
    pytest.param(
        {"attacks": 0},
        {"attacks": {"rate": 0.5}},
        {"attacks": {"rate": 0.5}},
        id="test_deep_merge_dict_replaces_scalar",
    ),
    pytest.param(
        {"range": 50},
        {"_012": {"range": 90}},
        {"range": 50},
        id="test_deep_merge_crosspath_key_skipped",
    ),
    pytest.param(
        {"range": 50},
        {"_12": {"range": 90}},
        {"range": 50, "_12": {"range": 90}},
        id="test_deep_merge_malformed_code_copied",
    ),
    pytest.param(
        {"range": 50},
        {},
        {"range": 50},
        id="test_deep_merge_empty_override",
    ),
]


def build_resolve_input(**changes: Any) -> dict[str, Any]:
    tower_data = copy.deepcopy(BASE_RESOLVE_INPUT)
    for key, value in changes.items():
        tower_data[key] = value
    return tower_data


def assert_not_aliased(results: dict[str, dict[str, Any]]) -> None:
    probe = copy.deepcopy(results)
    for code, stats in results.items():
        if "attacks" not in stats:
            continue
        stats["attacks"]["probe"] = "mutated"
        for other_code, other_stats in probe.items():
            if other_code != code:
                assert results[other_code] == other_stats
        stats["attacks"].pop("probe")


def resolve_checked(tower_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    original = copy.deepcopy(tower_data)
    results = resolve_all_codes(tower_data)
    assert tower_data == original
    assert_not_aliased(results)
    return results


def contains_code_key(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return any(CODE_PATTERN.match(key) or contains_code_key(item) for key, item in value.items())


@pytest.mark.parametrize(("base", "override", "expected"), DEEP_MERGE_CASES)
def test_deep_merge(base, override, expected):
    original_base = copy.deepcopy(base)
    original_override = copy.deepcopy(override)
    result = deep_merge(base, override)
    assert result == expected
    assert base == original_base
    assert override == original_override
    assert result is not base
    for key in override:
        if CODE_PATTERN.match(key):
            assert key not in result


def test_deep_merge_result_not_aliased_to_inputs():
    base = {"attacks": {"rate": 1.0}}
    override = {"extra": {"deep": 1}}
    result = deep_merge(base, override)
    result["attacks"]["rate"] = 99
    assert base == {"attacks": {"rate": 1.0}}


def test_resolve_all_codes_child_overrides_scalar():
    assert resolve_checked(build_resolve_input()) == BASE_RESOLVE_OUTPUT


def test_resolve_all_codes_ignores_non_code_key():
    results = resolve_checked({"range": 50, **build_resolve_input()})
    assert results == BASE_RESOLVE_OUTPUT
    assert "range" not in results


def test_resolve_all_codes_ignores_malformed_key():
    results = resolve_checked({"_01": {"range": 3}, **build_resolve_input()})
    assert results == BASE_RESOLVE_OUTPUT
    assert "_01" not in results


def test_resolve_all_codes_no_children():
    assert resolve_checked({"_100": {"range": 60}}) == {"_100": {"range": 60}}


def test_resolve_all_codes_grandchild_inherits_chain():
    tower_data = build_resolve_input()
    tower_data["_100"]["_110"]["_120"] = {"range": 80}
    results = resolve_checked(tower_data)
    assert results["_120"] == {"range": 80, "attacks": {"rate": 1, "count": 3}}
    assert results["_100"] == BASE_RESOLVE_OUTPUT["_100"]
    assert results["_110"] == BASE_RESOLVE_OUTPUT["_110"]


def test_resolve_all_codes_empty_child_inherits_all():
    tower_data = build_resolve_input()
    tower_data["_100"]["_110"] = {}
    results = resolve_checked(tower_data)
    assert results["_110"] == {"range": 60, "attacks": {"rate": 1, "count": 3}}


def test_resolve_all_codes_child_partial_dict_merge():
    tower_data = build_resolve_input()
    tower_data["_100"]["_110"] = {"attacks": {"rate": 2}}
    results = resolve_checked(tower_data)
    assert results["_110"] == {"range": 60, "attacks": {"rate": 2, "count": 3}}


def test_resolve_all_codes_siblings_independent():
    tower_data = build_resolve_input()
    tower_data["_100"]["_120"] = {"attacks": {"count": 9}}
    results = resolve_checked(tower_data)
    assert results["_120"] == {"range": 60, "attacks": {"rate": 1, "count": 9}}
    assert results["_110"] == BASE_RESOLVE_OUTPUT["_110"]
    assert results["_100"] == BASE_RESOLVE_OUTPUT["_100"]


def test_resolve_all_codes_top_level_siblings():
    results = resolve_checked(build_resolve_input(_010={"range": 40}))
    assert results["_010"] == {"range": 40}
    assert results["_100"] == BASE_RESOLVE_OUTPUT["_100"]
    assert results["_110"] == BASE_RESOLVE_OUTPUT["_110"]


def test_resolve_all_codes_empty():
    assert resolve_checked({}) == {}


@pytest.mark.parametrize(
    "tower_data",
    [
        build_resolve_input(),
        build_resolve_input(_010={"range": 40}),
    ],
    ids=["base", "top_level_siblings"],
)
def test_resolved_results_contain_no_crosspath_keys(tower_data):
    results = resolve_checked(tower_data)
    assert not any(contains_code_key(stats) for stats in results.values())


def test_resolve_then_extract_uses_inherited_mask() -> None:
    from btd6.etl.extract import extract_row
    from tests.factories import StatsFactory

    parent = StatsFactory(mask=8, pierce=3)
    tower_data = {"_100": {**parent, "_110": {"range": 70}}}
    resolved = resolve_all_codes(tower_data)
    row = extract_row("_110", resolved["_110"])
    assert (row["damage_type"], row["projectile_pierce"], row["range"]) == ("Fire", 3, 70)
