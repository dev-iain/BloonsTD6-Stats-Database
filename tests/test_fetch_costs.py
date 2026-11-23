from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from btd6.etl import fetch
from btd6.etl.towers import MAGIC_TOWERS

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "costs_super_monkey_cargo.json"
TOWER_PARAMS = {
    "action": "cargoquery",
    "tables": "btd6_towers",
    "fields": "name,cost,category",
    "where": "name='Super Monkey'",
}
UPGRADE_PARAMS = {
    "action": "cargoquery",
    "tables": "btd6_upgrades",
    "fields": "tower,path,tier,cost,name",
    "where": "tower='Super Monkey'",
    "limit": 500,
}


class FakeWiki:
    def __init__(self, towers: dict[str, Any], upgrades: dict[str, Any]) -> None:
        self.towers = towers
        self.upgrades = upgrades
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **params: Any) -> dict[str, Any]:
        self.calls.append(params)
        return self.towers if params["tables"] == "btd6_towers" else self.upgrades


InstallWiki = Callable[..., FakeWiki]


@pytest.fixture
def raw_responses() -> dict[str, Any]:
    return copy.deepcopy(json.loads(FIXTURE_PATH.read_text()))


@pytest.fixture
def install_wiki(monkeypatch: pytest.MonkeyPatch, raw_responses: dict[str, Any]) -> InstallWiki:
    def install(
        towers: dict[str, Any] | None = None, upgrades: dict[str, Any] | None = None
    ) -> FakeWiki:
        fake = FakeWiki(
            raw_responses["towers"] if towers is None else towers,
            raw_responses["upgrades"] if upgrades is None else upgrades,
        )
        monkeypatch.setattr(fetch, "wiki_api", fake)
        return fake

    return install


def test_fetch_costs_base_cost_and_category(install_wiki: InstallWiki) -> None:
    install_wiki()
    result = fetch.fetch_costs("Super Monkey")
    assert result["base_cost"] == 2500
    assert result["category"] == "Magic"
    assert set(result) == {"base_cost", "category", "upgrades"}


def test_fetch_costs_upgrade_rows(install_wiki: InstallWiki) -> None:
    install_wiki()
    upgrades = fetch.fetch_costs("Super Monkey")["upgrades"]
    assert len(upgrades) == 15
    by_key = {(row["path"], row["tier"]): row for row in upgrades}
    assert len(by_key) == 15
    assert by_key[(1, 1)] == {"path": 1, "tier": 1, "cost": 2000, "name": "Laser Blasts"}
    assert [by_key[(1, tier)]["cost"] for tier in range(1, 6)] == [
        2000,
        2500,
        20000,
        100000,
        500000,
    ]
    assert [by_key[(2, tier)]["cost"] for tier in range(1, 6)] == [1500, 1900, 7500, 25000, 70000]
    assert [by_key[(3, tier)]["cost"] for tier in range(1, 6)] == [3000, 1200, 5600, 55555, 165650]


def test_fetch_costs_converts_strings_to_ints(install_wiki: InstallWiki) -> None:
    install_wiki()
    result = fetch.fetch_costs("Super Monkey")
    assert type(result["base_cost"]) is int
    for row in result["upgrades"]:
        assert type(row["path"]) is int
        assert type(row["tier"]) is int
        assert type(row["cost"]) is int
        assert isinstance(row["name"], str)


def test_fetch_costs_exact_query_params(install_wiki: InstallWiki) -> None:
    fake = install_wiki()
    fetch.fetch_costs("Super Monkey")
    assert len(fake.calls) == 2
    assert TOWER_PARAMS in fake.calls
    assert UPGRADE_PARAMS in fake.calls


@pytest.mark.parametrize("tower_name", MAGIC_TOWERS)
def test_fetch_costs_where_clause_uses_tower_name(
    install_wiki: InstallWiki, tower_name: str
) -> None:
    fake = install_wiki()
    fetch.fetch_costs(tower_name)
    wheres = sorted(call["where"] for call in fake.calls)
    assert wheres == sorted([f"name='{tower_name}'", f"tower='{tower_name}'"])


@pytest.mark.parametrize(
    "tower_name",
    [
        "Dart Monkey",
        "",
        "super monkey",
        "Super Monkey'",
        "Super Monkey' OR 1=1 --",
        "Wizard'Monkey",
    ],
)
def test_fetch_costs_rejects_bad_name_without_query(
    install_wiki: InstallWiki, tower_name: str
) -> None:
    fake = install_wiki()
    with pytest.raises(ValueError):
        fetch.fetch_costs(tower_name)
    assert fake.calls == []


@given(tower_name=st.text().filter(lambda name: name not in MAGIC_TOWERS))
def test_fetch_costs_never_queries_unknown_tower(tower_name: str) -> None:
    calls: list[dict[str, Any]] = []
    original = fetch.wiki_api
    fetch.wiki_api = lambda **params: calls.append(params) or {}
    try:
        with pytest.raises(ValueError):
            fetch.fetch_costs(tower_name)
    finally:
        fetch.wiki_api = original
    assert calls == []


def test_fetch_costs_empty_tower_result(install_wiki: InstallWiki) -> None:
    install_wiki(towers={"cargoquery": []})
    with pytest.raises(ValueError):
        fetch.fetch_costs("Super Monkey")


def test_fetch_costs_empty_upgrade_result(install_wiki: InstallWiki) -> None:
    install_wiki(upgrades={"cargoquery": []})
    with pytest.raises(ValueError):
        fetch.fetch_costs("Super Monkey")


@pytest.mark.parametrize("failing", ["towers", "upgrades"])
def test_fetch_costs_error_response(install_wiki: InstallWiki, failing: str) -> None:
    error = {"error": {"code": "internal_api_error", "info": "boom"}}
    install_wiki(**{failing: error})
    with pytest.raises(ValueError):
        fetch.fetch_costs("Super Monkey")


@pytest.mark.parametrize("failing", ["towers", "upgrades"])
def test_fetch_costs_error_key_with_rows_still_raises(
    install_wiki: InstallWiki, raw_responses: dict[str, Any], failing: str
) -> None:
    response = raw_responses[failing]
    response["error"] = {"code": "warning", "info": "partial"}
    install_wiki(**{failing: response})
    with pytest.raises(ValueError):
        fetch.fetch_costs("Super Monkey")


def test_fetch_costs_path_and_tier_in_range(install_wiki: InstallWiki) -> None:
    install_wiki()
    for row in fetch.fetch_costs("Super Monkey")["upgrades"]:
        assert 1 <= row["path"] <= 3
        assert 1 <= row["tier"] <= 5
