from __future__ import annotations

from pathlib import Path

import pytest

from btd6.etl.fetch import PROJECT_ROOT


@pytest.fixture
def repo_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def golden_csv_path(repo_root: Path) -> Path:
    return repo_root / "data.csv"
