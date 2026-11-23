from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest

from btd6.ui import app

REPO_ROOT = Path(__file__).resolve().parents[2]
COMING_SOON = "Coming soon"


def descendants(widget: tk.Misc) -> list[tk.Misc]:
    found: list[tk.Misc] = []
    for child in widget.winfo_children():
        found.append(child)
        found.extend(descendants(child))
    return found


def find_notebook(root: tk.Misc) -> ttk.Notebook:
    notebooks = [item for item in descendants(root) if isinstance(item, ttk.Notebook)]
    assert len(notebooks) == 1
    return notebooks[0]


def tab_texts(notebook: ttk.Notebook) -> list[str]:
    return [notebook.tab(index, "text") for index in range(notebook.index("end"))]


def label_texts(widget: tk.Misc) -> list[str]:
    return [
        str(item.cget("text"))
        for item in descendants(widget)
        if isinstance(item, (ttk.Label, tk.Label))
    ]


@pytest.fixture
def window(tmp_path: Path):
    try:
        root = app.build_window(str(tmp_path / "btd6.db"))
    except tk.TclError:
        pytest.skip("no display available")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


def test_app_exposes_build_window_and_main() -> None:
    assert callable(getattr(app, "build_window", None))
    assert callable(getattr(app, "main", None))


def test_build_window_tab_titles(window: tk.Tk) -> None:
    assert tab_texts(find_notebook(window)) == ["Search", "Rounds", "Rankings"]


@pytest.mark.parametrize("index", [1, 2], ids=["rounds", "rankings"])
def test_build_window_placeholder_tabs(window: tk.Tk, index: int) -> None:
    notebook = find_notebook(window)
    tab = notebook.nametowidget(notebook.tabs()[index])
    assert COMING_SOON in label_texts(tab)


def test_build_window_search_tab_has_no_placeholder(window: tk.Tk) -> None:
    notebook = find_notebook(window)
    assert COMING_SOON not in label_texts(notebook.nametowidget(notebook.tabs()[0]))


class SpyConnection:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1

    def __getattr__(self, name: str):
        raise AttributeError(name)


def test_main_closes_connection_on_window_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = SpyConnection()
    monkeypatch.setattr(app, "connect", lambda *args, **kwargs: spy, raising=False)

    def close_window(root: tk.Tk) -> None:
        root.tk.call(root.protocol("WM_DELETE_WINDOW"))

    monkeypatch.setattr(tk.Tk, "mainloop", close_window)
    try:
        exit_code = app.main(str(tmp_path / "btd6.db"))
    except tk.TclError:
        pytest.skip("no display available")
    assert exit_code == 0
    assert spy.close_calls == 1


def run_isolated(code: str) -> subprocess.CompletedProcess[str]:
    prelude = f"import sys; sys.path.insert(0, {str(REPO_ROOT)!r})\n"
    return subprocess.run(
        [sys.executable, "-c", prelude + code], capture_output=True, text=True, timeout=60
    )


def test_import_btd6_ui_creates_no_window() -> None:
    code = (
        "import tkinter\n"
        "def boom(*args, **kwargs):\n"
        "    raise AssertionError('window created at import')\n"
        "tkinter.Tk = boom\n"
        "import btd6.ui\n"
        "import btd6.ui.app\n"
    )
    result = run_isolated(code)
    assert result.returncode == 0, result.stderr


def test_import_btd6_ui_does_not_import_tkinter() -> None:
    result = run_isolated("import sys, btd6.ui\nassert 'tkinter' not in sys.modules\n")
    assert result.returncode == 0, result.stderr
