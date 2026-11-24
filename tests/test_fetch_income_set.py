from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

from btd6.etl import fetch
from btd6.etl.fetch import DEFAULT_INCOME_SET, fetch_income_set
from tests.test_fetch_roundset import FakeResponse, build_envelope

TITLE_PREFIX = "JSON:Bloons TD 6/Rounds/"
FIXTURE = Path(__file__).parent / "fixtures" / "default_income_set.json"
EMPTY_SET = {"thresholds": {"items": []}, "finalMultiplier": 0.02}


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    recorded: list[dict[str, Any]] = []
    envelope = build_envelope(json.dumps(EMPTY_SET))

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        recorded.append({"url": url, **kwargs})
        return FakeResponse(envelope)

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    return recorded


def test_fetch_income_set_default(calls: list[dict[str, Any]]) -> None:
    assert fetch_income_set() == EMPTY_SET
    assert DEFAULT_INCOME_SET == "DefaultIncomeSet"
    assert calls[0]["params"]["titles"] == "JSON:Bloons TD 6/Rounds/DefaultIncomeSet"


def test_fetch_income_set_custom_name(calls: list[dict[str, Any]]) -> None:
    fetch_income_set("AlternateIncomeSet")
    assert calls[0]["params"]["titles"] == f"{TITLE_PREFIX}AlternateIncomeSet"


def test_fetch_income_set_missing_page(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = {"query": {"pages": [{"missing": True}]}}
    monkeypatch.setattr(fetch.requests, "get", lambda *args, **kwargs: FakeResponse(missing))
    with pytest.raises(ValueError, match='Income set "DefaultIncomeSet" not found on the wiki'):
        fetch_income_set()


def test_fetch_income_set_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    error = requests.HTTPError("500 Server Error")
    monkeypatch.setattr(fetch.requests, "get", lambda *args, **kwargs: FakeResponse({}, error))
    with pytest.raises(requests.HTTPError):
        fetch_income_set()


def test_fetch_income_set_returns_real_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope = build_envelope(FIXTURE.read_text())
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: FakeResponse(envelope))
    income_set = fetch_income_set()
    assert income_set["finalMultiplier"] == 0.02
    assert len(income_set["thresholds"]["items"]) == 6
