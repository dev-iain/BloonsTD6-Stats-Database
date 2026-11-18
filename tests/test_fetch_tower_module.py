from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

from btd6.etl import fetch

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "wiki_super_monkey_response.json"


class FakeResponse:
    def __init__(self, payload: dict[str, Any], error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error

    def json(self) -> dict[str, Any]:
        return self.payload


@pytest.fixture
def envelope() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text())


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, envelope: dict[str, Any]) -> list[dict[str, Any]]:
    recorded: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        recorded.append({"url": url, **kwargs})
        return FakeResponse(envelope)

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    return recorded


def test_parsed_result_equals_inner_json(calls, envelope) -> None:
    inner = json.loads(envelope["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"])
    assert fetch.fetch_tower_module("Super Monkey") == inner
    assert len(calls) == 1


def test_fixture_is_double_encoded(envelope) -> None:
    content = envelope["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
    assert isinstance(content, str)
    assert isinstance(json.loads(content), dict)


def test_wiki_api_adds_format_json_and_timeout(calls) -> None:
    fetch.wiki_api(action="query")
    assert calls[0]["url"] == fetch.API_URL
    assert calls[0]["params"] == {"action": "query", "format": "json"}
    assert calls[0]["timeout"] > 0


def test_fetch_tower_module_requests_tower_title(calls) -> None:
    fetch.fetch_tower_module("Super Monkey")
    assert calls[0]["params"]["titles"] == "Module:BTD6 stats/Super Monkey/new"


def test_http_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    error = requests.HTTPError("500 Server Error")
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: FakeResponse({}, error))
    with pytest.raises(requests.HTTPError):
        fetch.fetch_tower_module("Super Monkey")


def test_missing_page_currently_raises_key_error(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = {"query": {"pages": [{"missing": True}]}}
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: FakeResponse(missing))
    with pytest.raises(KeyError):
        fetch.fetch_tower_module("Not A Tower")


def test_network_guard_fails_unmocked_get() -> None:
    with pytest.raises(RuntimeError, match="Network access is blocked"):
        requests.get("https://example.com")


def test_wiki_api_timeout_is_thirty_seconds(calls) -> None:
    fetch.wiki_api(action="query")
    assert calls[0]["timeout"] == 30


def test_fetch_tower_module_sends_exact_params(calls) -> None:
    fetch.fetch_tower_module("Super Monkey")
    assert calls[0]["params"] == {
        "action": "query",
        "titles": "Module:BTD6 stats/Super Monkey/new",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "formatversion": 2,
        "format": "json",
    }
