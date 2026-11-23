from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from btd6 import cli
from btd6.etl.fetch import PROJECT_ROOT
from btd6.ui import launcher


def test_default_database_matches_project_database() -> None:
    assert launcher.DEFAULT_DATABASE_PATH == PROJECT_ROOT / "btd6.db"


def test_launch_without_display_exits_1_with_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import tkinter

    def no_display(*args: Any, **kwargs: Any) -> None:
        raise tkinter.TclError("no display name")

    monkeypatch.setattr(tkinter, "Tk", no_display)
    assert launcher.launch("x.db") == 1
    assert "display" in capsys.readouterr().err


def test_launch_without_tkinter_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "tkinter", None)
    assert launcher.launch("x.db") == 1
    assert "tkinter" in capsys.readouterr().err


def test_cli_ui_subcommand_passes_db(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(launcher, "launch", lambda path: seen.append(path) or 0)
    assert cli.main(["--db", "custom.db", "ui"]) == 0
    assert seen == ["custom.db"]


def test_cli_without_subcommand_still_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 2
    assert "usage" in capsys.readouterr().err


def test_module_main_passes_db(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(launcher, "launch", lambda path: seen.append(path) or 0)
    assert launcher.main(["--db", "other.db"]) == 0
    assert seen == ["other.db"]


def run_import_check(statement: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", statement],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.parametrize("module", ["btd6.cli", "btd6.ui.presenters", "btd6.ui.worker"])
def test_non_ui_modules_never_import_tkinter(module: str) -> None:
    code = f"import sys, {module}; print('tkinter' in sys.modules)"
    assert run_import_check(code) == "False"


def test_ui_modules_do_not_import_cli_or_pandas() -> None:
    code = (
        "import sys, btd6.ui.app, btd6.ui.services; "
        "print('pandas' in sys.modules or 'btd6.cli' in sys.modules)"
    )
    assert run_import_check(code) == "False"
