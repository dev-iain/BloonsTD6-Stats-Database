from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from btd6.api import create_app
from btd6.db import connect
from btd6.query import UpgradeFilters, search_upgrades
from tests.test_ranking import UPGRADE_STATS, build_database


@pytest.fixture
def db_file(tmp_path: Path) -> str:
    path = tmp_path / "btd6.db"
    memory = build_database(UPGRADE_STATS)
    disk = connect(str(path))
    memory.backup(disk)
    disk.close()
    memory.close()
    return str(path)


@pytest.fixture
def client(db_file: str) -> TestClient:
    return TestClient(create_app(db_file))


def test_upgrades_returns_every_row_without_filters(client: TestClient, db_file: str) -> None:
    connection = connect(db_file)
    expected = len(search_upgrades(connection, UpgradeFilters()))
    connection.close()
    response = client.get("/api/upgrades")
    assert response.status_code == 200
    assert len(response.json()["rows"]) == expected


def test_upgrades_rows_carry_raw_columns(client: TestClient) -> None:
    row = client.get("/api/upgrades", params={"sort": "path"}).json()["rows"][0]
    assert row["tower_name"] == "Super Monkey"
    assert {"path", "projectile_damage", "can_pop_lead", "damage_type"} <= set(row)


def test_upgrades_applies_numeric_filter(client: TestClient) -> None:
    rows = client.get("/api/upgrades", params={"min_pierce": 6}).json()["rows"]
    assert rows
    assert all(row["projectile_pierce"] >= 6 for row in rows)


def test_upgrades_applies_sort_and_limit(client: TestClient) -> None:
    rows = client.get("/api/upgrades", params={"sort": "projectile_pierce", "limit": 2}).json()[
        "rows"
    ]
    assert [row["projectile_pierce"] for row in rows] == [8, 6]


def test_upgrades_applies_damage_type_filter(client: TestClient) -> None:
    rows = client.get("/api/upgrades", params={"damage_type": "Plasma"}).json()["rows"]
    assert [row["path"] for row in rows] == ["3-0-0"]


def test_upgrades_rejects_unknown_sort_column(client: TestClient) -> None:
    response = client.get("/api/upgrades", params={"sort": "nonsense"})
    assert response.status_code == 422
    assert "Cannot sort by" in response.json()["error"]


def test_upgrades_rejects_negative_minimum(client: TestClient) -> None:
    response = client.get("/api/upgrades", params={"min_damage": -1})
    assert response.status_code == 422
    assert "min_damage" in response.json()["error"]


def test_upgrades_rejects_invalid_pop_choice(client: TestClient) -> None:
    response = client.get("/api/upgrades", params={"lead": "maybe"})
    assert response.status_code == 422


def test_rankings_orders_by_metric_descending(client: TestClient) -> None:
    rows = client.get("/api/rankings", params={"metric": "dps"}).json()["rows"]
    scores = [row["dps"] for row in rows]
    assert scores == sorted(scores, reverse=True)


def test_rankings_include_cost_and_per_dollar(client: TestClient) -> None:
    row = client.get("/api/rankings").json()["rows"][0]
    assert {"tower_name", "path", "total_cost", "dps", "damage_per_dollar"} <= set(row)


def test_rankings_respects_limit(client: TestClient) -> None:
    rows = client.get("/api/rankings", params={"limit": 1}).json()["rows"]
    assert len(rows) == 1


def test_rankings_rejects_unknown_metric(client: TestClient) -> None:
    response = client.get("/api/rankings", params={"metric": "vibes"})
    assert response.status_code == 422
    assert "Cannot rank by" in response.json()["error"]


def test_rankings_rejects_unknown_difficulty(client: TestClient) -> None:
    response = client.get("/api/rankings", params={"difficulty": "nightmare"})
    assert response.status_code == 422


def test_damage_types_lists_seeded_names(client: TestClient) -> None:
    names = client.get("/api/damage-types").json()["damage_types"]
    assert {"Sharp", "Plasma", "Energy", "Normal"} <= set(names)


def test_missing_database_returns_503(tmp_path: Path) -> None:
    missing = TestClient(create_app(str(tmp_path / "absent.db")))
    response = missing.get("/api/upgrades")
    assert response.status_code == 503
    assert "python -m btd6 load" in response.json()["error"]


def test_root_serves_the_frontend_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "BTD6" in response.text


def test_frontend_assets_are_served(client: TestClient) -> None:
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
