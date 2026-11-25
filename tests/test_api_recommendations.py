from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from btd6.api import create_app
from btd6.db import connect
from btd6.recommend import OwnedTower, recommend
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


def expected_rows(tmp_path: Path, *args: Any, **options: Any) -> list[dict[str, Any]]:
    connection = connect(str(tmp_path / "btd6.db"))
    try:
        return [
            {**asdict(result), "reasons": list(result.reasons)}
            for result in recommend(connection, *args, **options)
        ]
    finally:
        connection.close()


def test_recommendations_round_63(client: TestClient, tmp_path: Path) -> None:
    response = client.get(URL, params={"round": 63, "money": 100000, "horizon": 1})

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [row["path"] for row in rows] == ["3-0-0", "0-0-4"]
    assert isinstance(rows[0]["reasons"], list)
    assert rows == expected_rows(tmp_path, 63, 100000, horizon=1)
    assert {"effective_pierce", "first_leak_round"} <= set(rows[0])


def test_recommendations_default_horizon(client: TestClient, tmp_path: Path) -> None:
    response = client.get(URL, params={"round": 100, "money": 100000})

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert rows == expected_rows(tmp_path, 100, 100000)
    assert rows[0]["path"] == "0-0-4"
    assert {row["path"]: row["first_leak_round"] for row in rows} == {
        "0-0-4": None,
        "0-0-0": 101,
        "1-0-0": 101,
        "3-0-0": 101,
    }
    assert rows[1]["reasons"][-1] == "fails_camo_at_101"


def test_recommendations_horizon_one_has_no_leaks(client: TestClient, tmp_path: Path) -> None:
    response = client.get(URL, params={"round": 100, "money": 100000, "horizon": 1})

    rows = response.json()["rows"]
    assert rows == expected_rows(tmp_path, 100, 100000, horizon=1)
    assert {row["first_leak_round"] for row in rows} == {None}


def test_recommendations_limit_one(client: TestClient) -> None:
    response = client.get(URL, params={"round": 40, "money": 100000, "limit": 1, "horizon": 1})

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["path"] == "0-0-0"


def test_recommendations_hard_difficulty(client: TestClient) -> None:
    params = {"round": 63, "money": 100000, "difficulty": "hard", "horizon": 1}
    response = client.get(URL, params=params)

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
        ({"round": 63, "money": 100000, "horizon": 0}, "horizon must be at least 1, got 0"),
        (
            {"round": 63, "money": 100000, "horizon": "abc"},
            "horizon must be a whole number, got 'abc'",
        ),
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


def owned_params(*owned: str, **extra: Any) -> list[tuple[str, Any]]:
    base = {"round": 1, "money": 100000, "horizon": 1, **extra}
    return [*base.items(), *[("owned", entry) for entry in owned]]


def test_recommendations_include_upgrade_from_field(client: TestClient) -> None:
    rows = client.get(URL, params={"round": 1, "money": 100000}).json()["rows"]

    assert {row["upgrade_from"] for row in rows} == {None}
    assert list(rows[0])[:4] == ["tower_name", "path", "total_cost", "upgrade_from"]


def test_recommendations_owned_single(client: TestClient, tmp_path: Path) -> None:
    response = client.get(URL, params=owned_params("Super Monkey 0-0-0"))

    rows = response.json()["rows"]
    assert response.status_code == 200
    owned = [OwnedTower("Super Monkey", "0-0-0")]
    assert rows == expected_rows(tmp_path, 1, 100000, horizon=1, owned=owned)
    upgrades = {row["path"]: row for row in rows if row["upgrade_from"]}
    assert upgrades["3-0-0"]["total_cost"] == 24500
    assert upgrades["3-0-0"]["upgrade_from"] == "0-0-0"
    assert "upgrades_owned" in upgrades["3-0-0"]["reasons"]


def test_recommendations_owned_repeated(client: TestClient, tmp_path: Path) -> None:
    response = client.get(URL, params=owned_params("Super Monkey 0-0-0", "Super Monkey 1-0-0"))

    rows = response.json()["rows"]
    assert response.status_code == 200
    owned = [OwnedTower("Super Monkey", "0-0-0"), OwnedTower("Super Monkey", "1-0-0")]
    assert rows == expected_rows(tmp_path, 1, 100000, horizon=1, owned=owned)
    origins = {row["upgrade_from"] for row in rows if row["path"] == "3-0-0"}
    assert origins == {None, "0-0-0", "1-0-0"}


def test_recommendations_owned_unknown_tower_is_ignored(client: TestClient, tmp_path: Path) -> None:
    response = client.get(URL, params=owned_params("Banana Farm 2-0-0"))

    assert response.status_code == 200
    assert response.json()["rows"] == expected_rows(tmp_path, 1, 100000, horizon=1)


@pytest.mark.parametrize(("text", "expected"), [("true", True), ("1", True), ("false", False)])
def test_recommendations_one_per_tower(
    client: TestClient, tmp_path: Path, text: str, expected: bool
) -> None:
    response = client.get(URL, params={**base_params(), "one_per_tower": text})

    rows = response.json()["rows"]
    assert response.status_code == 200
    assert rows == expected_rows(tmp_path, 1, 100000, horizon=1, one_per_tower=expected)
    assert len(rows) == (1 if expected else 4)


def test_recommendations_one_per_tower_blank_is_false(client: TestClient) -> None:
    response = client.get(URL, params={**base_params(), "one_per_tower": ""})

    assert len(response.json()["rows"]) == 4


def base_params() -> dict[str, Any]:
    return {"round": 1, "money": 100000, "horizon": 1}


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (
            [*base_params().items(), ("one_per_tower", "yes")],
            "one_per_tower must be true or false, got 'yes'",
        ),
        (
            [*base_params().items(), ("owned", "Ninja")],
            "owned must be '<tower name> X-Y-Z', got 'Ninja'",
        ),
        (
            [*base_params().items(), ("owned", "Super Monkey 0-0-0"), ("owned", "Ninja")],
            "owned must be '<tower name> X-Y-Z', got 'Ninja'",
        ),
        (
            [*base_params().items(), ("owned", "Super Monkey 1-2")],
            "owned must be '<tower name> X-Y-Z', got 'Super Monkey 1-2'",
        ),
    ],
    ids=["one_per_tower", "owned", "second_owned", "short_path"],
)
def test_recommendations_new_params_invalid_is_422(
    client: TestClient, params: list[tuple[str, Any]], message: str
) -> None:
    response = client.get(URL, params=params)

    assert response.status_code == 422
    assert response.json()["error"] == message


def test_recommendations_owned_path_digit_out_of_range_is_422(client: TestClient) -> None:
    response = client.get(URL, params=owned_params("Super Monkey 6-0-0"))

    assert response.status_code == 422
