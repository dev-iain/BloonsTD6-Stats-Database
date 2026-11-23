from __future__ import annotations

from pathlib import Path

import pytest

from btd6.cli import build_parser, main
from btd6.etl.fetch import PROJECT_ROOT
from btd6.ui import app


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "btd6.db")


@pytest.fixture
def app_main_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def spy(database_path: str) -> int:
        calls.append(database_path)
        return 7

    monkeypatch.setattr(app, "main", spy, raising=False)
    return calls


@pytest.mark.parametrize("command", ["gui", "ui"])
def test_main_gui_dispatches_to_app_main(db_path: str, app_main_calls: list[str], command) -> None:
    assert main(["--db", db_path, command]) == 7
    assert app_main_calls == [db_path]


def test_main_gui_default_database(app_main_calls: list[str]) -> None:
    assert main(["gui"]) == 7
    assert app_main_calls == [str(PROJECT_ROOT / "btd6.db")]


def test_main_gui_rejects_search_options(
    db_path: str, app_main_calls: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--db", db_path, "gui", "--min-pierce", "1"])
    assert excinfo.value.code == 2
    assert capsys.readouterr().err.splitlines()[-1] == (
        "btd6: error: unrecognized arguments: --min-pierce 1"
    )
    assert app_main_calls == []


def test_build_parser_lists_gui() -> None:
    assert "gui" in build_parser().format_help()


def test_build_parser_accepts_gui_and_ui() -> None:
    parser = build_parser()
    assert parser.parse_args(["gui"]).command in {"gui"}
    assert parser.parse_args(["ui"]).command in {"gui", "ui"}


def test_main_gui_unexpected_error(
    db_path: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(database_path: str) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(app, "main", boom, raising=False)
    assert main(["--db", db_path, "gui"]) == 1
    assert capsys.readouterr().err.strip() == "Unexpected error: boom"
