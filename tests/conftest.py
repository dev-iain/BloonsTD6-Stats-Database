from __future__ import annotations

from pathlib import Path

import pytest
import requests

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
