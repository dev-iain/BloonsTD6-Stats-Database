from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from btd6.etl import extract, fetch
from btd6.etl.extract import extract_row, first_of, path_from_code
from tests.factories import StatsFactory

TOWER_DATA: dict[str, Any] = {"_100": StatsFactory(mask=8, pierce=3)}


def test_first_of_name_listed_without_entry() -> None:
    assert first_of({"_order": ["a"]}) == ("a", {})


def test_extract_row_attack_listed_without_entry() -> None:
    row = extract_row("_000", {"attacks": {"_order": ["a"]}})
    assert row["attack_rate"] is None


def test_path_from_code_only_strips_underscore() -> None:
    assert path_from_code("_X12") == "X-1-2"


def test_can_hit_camo_defaults_to_true() -> None:
    row = extract_row("_000", {})
    assert row["can_hit_camo"] is True


def test_pick_fields_deep_copies() -> None:
    source = {"a": {"x": [1]}}
    result = fetch.pick_fields(source, ("a",))
    result["a"]["x"].append(2)
    assert source == {"a": {"x": [1]}}


def test_write_resolved_json_default_path_and_format(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requested: list[str] = []

    def stub_fetch(name: str) -> dict[str, Any]:
        requested.append(name)
        return TOWER_DATA

    monkeypatch.setattr(fetch, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(fetch, "fetch_tower_module", stub_fetch)
    written = fetch.write_resolved_json("Super Monkey")
    expected = {"_100": fetch.trim_stats(TOWER_DATA["_100"])}
    assert requested == ["Super Monkey"]
    assert written == tmp_path / "data.json"
    assert written.read_text() == json.dumps(expected, indent=4)


def test_export_csv_explicit_paths(tmp_path: Path) -> None:
    json_path = tmp_path / "in.json"
    csv_path = tmp_path / "out.csv"
    json_path.write_text(json.dumps({"_100": TOWER_DATA["_100"]}))
    frame = extract.export_csv(json_path, csv_path)
    reloaded = pd.read_csv(csv_path, index_col="path")
    assert frame.index.name == "path"
    assert list(reloaded.index) == ["1-0-0"]
    assert reloaded.loc["1-0-0", "damage_type"] == "Fire"


def test_export_csv_default_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "data.json").write_text(json.dumps({"_100": TOWER_DATA["_100"]}))
    monkeypatch.setattr(extract, "PROJECT_ROOT", tmp_path)
    extract.export_csv()
    assert (tmp_path / "data.csv").exists()
