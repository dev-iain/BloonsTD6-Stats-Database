from __future__ import annotations

import tkinter as tk
from collections.abc import Iterator

import pytest


@pytest.fixture
def tk_root() -> Iterator[tk.Tk]:
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass
