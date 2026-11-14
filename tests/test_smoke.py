from __future__ import annotations

from pathlib import Path

from btd6.etl import extract, fetch


def test_path_from_code_converts_wiki_code() -> None:
    assert extract.path_from_code("_023") == "0-2-3"
    assert fetch.PROJECT_ROOT.is_dir()


def test_repo_root_is_directory(repo_root: Path) -> None:
    assert repo_root.is_dir()


def test_golden_csv_exists(golden_csv_path: Path) -> None:
    assert golden_csv_path.is_file()
