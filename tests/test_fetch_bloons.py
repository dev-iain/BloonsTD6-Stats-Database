from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

from btd6.etl import fetch
from btd6.etl.fetch import fetch_bloons

FIELDS = "id,name,health,health_fort,layers,rbe,rbe_fort,is_moab,speed,immunity,parent_of,child_of"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "bloons_cargo_response.json"
FIELD_NAMES = FIELDS.split(",")


def make_title(name: str) -> dict[str, str]:
    return {field: "" for field in FIELD_NAMES} | {"id": name.lower(), "name": name}


def make_page(titles: list[dict[str, str]]) -> dict[str, Any]:
    return {"cargoquery": [{"title": title} for title in titles]}


def make_numbered_page(start: int, count: int) -> dict[str, Any]:
    return make_page([make_title(f"Bloon{number}") for number in range(start, start + count)])


class FakeWiki:
    def __init__(self, pages: list[dict[str, Any] | Exception]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **params: Any) -> dict[str, Any]:
        self.calls.append(params)
        page = self.pages[len(self.calls) - 1]
        if isinstance(page, Exception):
            raise page
        return page

    @property
    def offsets(self) -> list[int]:
        return [call["offset"] for call in self.calls]


def install(monkeypatch: pytest.MonkeyPatch, pages: list[dict[str, Any] | Exception]) -> FakeWiki:
    fake = FakeWiki(pages)
    monkeypatch.setattr(fetch, "wiki_api", fake)
    return fake


def test_fetch_bloons_single_page(monkeypatch: pytest.MonkeyPatch) -> None:
    titles = [make_title(name) for name in ("Red", "Blue", "Green")]
    fake = install(monkeypatch, [make_page(titles)])

    rows = fetch_bloons()

    assert [row["name"] for row in rows] == ["Red", "Blue", "Green"]
    assert rows == titles
    assert fake.calls == [
        {
            "action": "cargoquery",
            "tables": "btd6_bloons",
            "fields": FIELDS,
            "limit": 500,
            "offset": 0,
        }
    ]


def test_fetch_bloons_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, [{"cargoquery": []}])

    with pytest.raises(ValueError, match="Wiki cargo query returned no rows"):
        fetch_bloons()


def test_fetch_bloons_exact_full_page(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install(monkeypatch, [make_numbered_page(0, 500), {"cargoquery": []}])

    assert len(fetch_bloons()) == 500
    assert fake.offsets == [0, 500]


def test_fetch_bloons_two_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install(monkeypatch, [make_numbered_page(0, 500), make_numbered_page(500, 120)])

    rows = fetch_bloons()

    assert len(rows) == 620
    assert rows[500]["name"] == "Bloon500"
    assert [row["name"] for row in rows] == [f"Bloon{number}" for number in range(620)]
    assert fake.offsets == [0, 500]


def test_fetch_bloons_cargo_error(monkeypatch: pytest.MonkeyPatch) -> None:
    error = {"error": {"code": "internal_api_error", "info": "Table missing"}}
    install(monkeypatch, [error])

    with pytest.raises(ValueError, match="^Wiki cargo query failed:.*Table missing"):
        fetch_bloons()


def test_fetch_bloons_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, [requests.HTTPError("503")])

    with pytest.raises(requests.HTTPError):
        fetch_bloons()


def test_fetch_bloons_missing_field_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    titles = [make_title(name) for name in ("Red", "Blue", "Green")]
    del titles[1]["speed"]
    install(monkeypatch, [make_page(titles)])

    rows = fetch_bloons()

    assert len(rows) == 3
    assert "speed" not in rows[1]
    assert "speed" in rows[0]


def test_fetch_bloons_error_on_second_page(monkeypatch: pytest.MonkeyPatch) -> None:
    error = {"error": {"info": "Table missing"}}
    install(monkeypatch, [make_numbered_page(0, 500), error])

    with pytest.raises(ValueError, match="Wiki cargo query failed"):
        fetch_bloons()


def test_fetch_bloons_never_calls_requests_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access outside wiki_api")

    monkeypatch.setattr(requests, "get", forbidden)
    install(monkeypatch, [make_page([make_title("Red")])])

    assert len(fetch_bloons()) == 1


def test_fetch_bloons_unwraps_captured_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    response = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    install(monkeypatch, [response])

    rows = fetch_bloons()

    assert {row["id"] for row in rows} == {"Red", "Blue", "Green", "Moab", "Zomg", "Ceramic"}


def test_fetch_bloons_normalizes_spaced_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    response = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    install(monkeypatch, [response])

    row = fetch_bloons()[0]

    assert {"health_fort", "rbe_fort", "is_moab", "parent_of", "child_of"} <= set(row)
    assert not any(" " in key for key in row)
