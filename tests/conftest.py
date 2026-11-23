from __future__ import annotations

import copy
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import requests

from btd6.db import connect
from btd6.db.seed import initialize_database
from btd6.etl import fetch
from btd6.etl.fetch import PROJECT_ROOT


@pytest.fixture
def repo_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def golden_csv_path(repo_root: Path) -> Path:
    return repo_root / "data.csv"


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse_request(*args, **kwargs):
        raise RuntimeError("Network access is blocked in tests; mock requests.get")

    monkeypatch.setattr(requests, "get", refuse_request)


@pytest.fixture
def database() -> Iterator[sqlite3.Connection]:
    connection = connect(":memory:")
    initialize_database(connection)
    yield connection
    connection.close()


@pytest.fixture
def super_monkey_resolved(repo_root: Path) -> dict[str, Any]:
    with open(repo_root / "tests" / "fixtures" / "super_monkey_resolved.json") as handle:
        return json.load(handle)


class OfflineCostsWiki:
    """Serves the Super Monkey Cargo fixture for any `fetch_costs` query."""

    def __init__(self) -> None:
        path = Path(__file__).parent / "fixtures" / "costs_super_monkey_cargo.json"
        self.responses = json.loads(path.read_text())

    def __call__(self, **params: Any) -> dict[str, Any]:
        key = "towers" if params["tables"] == "btd6_towers" else "upgrades"
        return copy.deepcopy(self.responses[key])


@pytest.fixture
def offline_costs_wiki(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch, "wiki_api", OfflineCostsWiki())
