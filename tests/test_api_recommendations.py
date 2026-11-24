from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from btd6.api import create_app
from btd6.db import connect
from btd6.recommend import recommend
from tests.income_fixture import save_connection
from tests.recommend_fixture import build_recommend_database

URL = "/api/recommendations"


def client_for(tmp_path: Path, with_rounds: bool = True) -> TestClient:
    source = build_recommend_database(with_rounds=with_rounds)
    path = save_connection(source, tmp_path / "btd6.db")
    source.close()
    return TestClient(create_app(path))


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return client_for(tmp_path)


def expected_rows(tmp_path: Path, *args: Any) -> list[dict[str, Any]]:
    connection = connect(str(tmp_path / "btd6.db"))
    try:
        return [
            {**asdict(result), "reasons": list(result.reasons)}
            for result in recommend(connection, *args)
        ]
    finally:
        connection.close()


def test_recommendations_round_63(client: TestClient, tmp_path: Path) -> None:
    response = client.get(URL, params={"round": 63, "money": 100000})

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [row["path"] for row in rows] == ["3-0-0", "0-0-4"]
    assert isinstance(rows[0]["reasons"], list)
    assert rows == expected_rows(tmp_path, 63, 100000)


def test_recommendations_limit_one(client: TestClient) -> None:
    response = client.get(URL, params={"round": 40, "money": 100000, "limit": 1})

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["path"] == "0-0-0"


def test_recommendations_hard_difficulty(client: TestClient) -> None:
    response = client.get(URL, params={"round": 63, "money": 100000, "difficulty": "hard"})

    assert response.status_code == 200
    first = response.json()["rows"][0]
    assert first["path"] == "3-0-0"
    assert first["total_cost"] == 29160


def test_recommendations_nothing_affordable(client: TestClient) -> None:
    response = client.get(URL, params={"round": 1, "money": 100})

    assert response.status_code == 200
    assert response.json() == {"rows": []}


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"round": 63, "money": -1}, "money must be 0 or more, got -1"),
        ({"round": 63, "money": "abc"}, "money must be a whole number, got 'abc'"),
        ({"round": 63}, "money is required"),
        ({"money": 100000}, "round is required"),
        ({"round": "abc", "money": 100000}, "round must be a whole number, got 'abc'"),
        ({"round": 63, "money": 100000, "limit": 0}, "limit must be at least 1, got 0"),
        ({"round": 150, "money": 100000}, "Round 150 is not loaded; loaded rounds are 1-101"),
    ],
)
def test_recommendations_invalid_input_is_422(
    client: TestClient, params: dict[str, Any], message: str
) -> None:
    response = client.get(URL, params=params)

    assert response.status_code == 422
    assert response.json()["error"] == message


def test_recommendations_invalid_difficulty_is_422(client: TestClient) -> None:
    response = client.get(URL, params={"round": 63, "money": 100000, "difficulty": "nightmare"})

    assert response.status_code == 422
    assert response.json()["error"]


def test_recommendations_without_round_data_is_404(tmp_path: Path) -> None:
    response = client_for(tmp_path, with_rounds=False).get(
        URL, params={"round": 63, "money": 100000}
    )

    assert response.status_code == 404
    assert response.json()["error"].startswith("No round data")


def test_recommendations_missing_database_is_503(tmp_path: Path) -> None:
    client = TestClient(create_app(str(tmp_path / "absent.db")))

    response = client.get(URL, params={"round": 63, "money": 100000})

    assert response.status_code == 503
    assert "python -m btd6 load" in response.json()["error"]
