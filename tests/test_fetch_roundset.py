from __future__ import annotations

import json
from typing import Any

import pytest
import requests

from btd6.etl import fetch
from btd6.etl.fetch import DEFAULT_ROUNDSET, fetch_roundset

TITLE_PREFIX = "JSON:Bloons TD 6/Rounds/"


class FakeResponse:
    def __init__(self, payload: dict[str, Any], error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error

    def json(self) -> dict[str, Any]:
        return self.payload


def build_envelope(content: str) -> dict[str, Any]:
    revision = {"slots": {"main": {"content": content}}}
    return {"query": {"pages": [{"revisions": [revision]}]}}


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    recorded: list[dict[str, Any]] = []
    envelope = build_envelope(json.dumps({"rounds": []}))

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        recorded.append({"url": url, **kwargs})
        return FakeResponse(envelope)

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    return recorded


def test_fetch_roundset_default(calls: list[dict[str, Any]]) -> None:
    assert fetch_roundset() == {"rounds": []}
    assert calls[0]["params"]["titles"] == f"{TITLE_PREFIX}{DEFAULT_ROUNDSET}"
    assert calls[0]["params"]["titles"] == "JSON:Bloons TD 6/Rounds/DefaultRoundSet"


def test_fetch_roundset_custom_name(calls: list[dict[str, Any]]) -> None:
    fetch_roundset("AlternateRoundSet")
    assert calls[0]["params"]["titles"] == "JSON:Bloons TD 6/Rounds/AlternateRoundSet"


def test_fetch_roundset_missing_page(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = {"query": {"pages": [{"missing": True}]}}
    monkeypatch.setattr(fetch.requests, "get", lambda *args, **kwargs: FakeResponse(missing))
    with pytest.raises(ValueError, match='Roundset "DefaultRoundSet" not found on the wiki'):
        fetch_roundset()


def test_fetch_roundset_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    error = requests.HTTPError("500 Server Error")
    monkeypatch.setattr(fetch.requests, "get", lambda *args, **kwargs: FakeResponse({}, error))
    with pytest.raises(requests.HTTPError):
        fetch_roundset()
