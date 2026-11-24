from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from btd6.api import create_app
from btd6.income import round_income
from btd6.threats import PROPERTY_NAMES, round_threats
from tests.income_fixture import build_connection, save_connection

LOADED_ROUNDS = 40


def client_for(tmp_path: Path, max_round: int | None, with_income: bool = True) -> TestClient:
    source = build_connection(max_round, with_income=with_income)
    path = save_connection(source, tmp_path / "btd6.db")
    source.close()
    return TestClient(create_app(path))


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return client_for(tmp_path, LOADED_ROUNDS)


def test_round_returns_summary_flags(client: TestClient) -> None:
    body = client.get("/api/rounds/40").json()
    assert body["round"] == 40
    assert body["summary"]["has_moab"] is True
    assert {"total_bloons", "total_rbe", "has_camo", "has_lead", "has_ceramic"} <= set(
        body["summary"]
    )


def test_round_returns_groups_in_order(client: TestClient) -> None:
    groups = client.get("/api/rounds/1").json()["groups"]
    assert groups
    assert [group["group_index"] for group in groups] == list(range(len(groups)))
    assert {"bloon", "count", "is_camo", "is_regrow", "is_fortified", "rbe"} <= set(groups[0])


def test_round_flags_match_round_contents(client: TestClient) -> None:
    summary = client.get("/api/rounds/1").json()["summary"]
    assert summary["has_moab"] is False
    assert summary["has_camo"] is False


def test_round_returns_income(client: TestClient, tmp_path: Path) -> None:
    income = client.get("/api/rounds/10").json()["income"]
    source = build_connection(LOADED_ROUNDS)
    expected = round_income(source, 10)
    assert income["pop_cash"] == pytest.approx(expected.pop_cash)
    assert income["end_bonus"] == expected.end_bonus
    assert income["total"] == pytest.approx(expected.total)


def test_round_income_is_null_without_income_data(tmp_path: Path) -> None:
    body = client_for(tmp_path, LOADED_ROUNDS, with_income=False).get("/api/rounds/10").json()
    assert body["income"] is None
    assert body["groups"]


@pytest.mark.parametrize("round_number", [0, LOADED_ROUNDS + 1, -3])
def test_round_out_of_range_is_422(client: TestClient, round_number: int) -> None:
    response = client.get(f"/api/rounds/{round_number}")
    assert response.status_code == 422
    assert "not loaded" in response.json()["error"] or "Round" in response.json()["error"]


def test_round_rejects_non_integer(client: TestClient) -> None:
    assert client.get("/api/rounds/abc").status_code == 422


def test_round_without_round_data_is_404(tmp_path: Path) -> None:
    response = client_for(tmp_path, None).get("/api/rounds/1")
    assert response.status_code == 404
    assert "No round data" in response.json()["error"]


def test_round_with_missing_database_is_503(tmp_path: Path) -> None:
    response = TestClient(create_app(str(tmp_path / "absent.db"))).get("/api/rounds/1")
    assert response.status_code == 503


def test_rounds_index_lists_loaded_range(client: TestClient) -> None:
    assert client.get("/api/rounds").json() == {"first": 1, "last": LOADED_ROUNDS}


def test_rounds_index_without_data_is_null(tmp_path: Path) -> None:
    assert client_for(tmp_path, None).get("/api/rounds").json() == {"first": None, "last": None}


def test_round_composition_merges_groups_of_the_same_bloon(client: TestClient) -> None:
    body = client.get("/api/rounds/5").json()
    spawned: dict[tuple[str, bool, bool, bool], int] = {}
    for group in body["groups"]:
        key = (group["bloon"], group["is_camo"], group["is_regrow"], group["is_fortified"])
        spawned[key] = spawned.get(key, 0) + group["count"]
    merged = {
        (e["bloon"], e["is_camo"], e["is_regrow"], e["is_fortified"]): e["count"]
        for e in body["composition"]
    }
    assert merged == spawned
    assert len(body["composition"]) < len(body["groups"])


def test_round_composition_counts_match_summary(client: TestClient) -> None:
    body = client.get("/api/rounds/40").json()
    assert sum(entry["count"] for entry in body["composition"]) == body["summary"]["total_bloons"]
    assert sum(entry["total_rbe"] for entry in body["composition"]) == body["summary"]["total_rbe"]


def test_round_composition_separates_modifiers(client: TestClient) -> None:
    keys = {
        (entry["bloon"], entry["is_camo"], entry["is_regrow"], entry["is_fortified"])
        for entry in client.get("/api/rounds/24").json()["composition"]
    }
    assert all(len(key) == 4 for key in keys)
    assert len(keys) == len(client.get("/api/rounds/24").json()["composition"])


def test_round_composition_is_ordered_by_total_rbe(client: TestClient) -> None:
    totals = [entry["total_rbe"] for entry in client.get("/api/rounds/40").json()["composition"]]
    assert totals == sorted(totals, reverse=True)


def test_round_returns_threats_matching_round_threats(tmp_path: Path) -> None:
    source = build_connection(LOADED_ROUNDS)
    path = save_connection(source, tmp_path / "btd6.db")
    expected = asdict(round_threats(source, 40))
    source.close()
    body = TestClient(create_app(path)).get("/api/rounds/40").json()
    assert body["threats"] == expected
    assert set(body["threats"]["property_share"]) == set(PROPERTY_NAMES)
    assert body["threats"]["moab_share"] > 0
