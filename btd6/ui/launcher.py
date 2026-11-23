from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "btd6.db"
NO_TKINTER_MESSAGE = (
    "The desktop interface needs Python's tkinter module, which is not installed. "
    "Install it (for example the python3-tk package) or use the command line instead."
)


def launch(database_path: str | Path) -> int:
    """Open the window and run until it closes. Returns a process exit code."""
    try:
        import tkinter as tk
    except ImportError:
        print(NO_TKINTER_MESSAGE, file=sys.stderr)
        return 1
    from btd6.ui.theme import enable_dpi_awareness

    enable_dpi_awareness()
    from btd6.ui import app

    try:
        return app.main(str(database_path))
    except tk.TclError as error:
        print(f"Could not open a window (is a display available?): {error}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m btd6.ui")
    parser.add_argument("--db", default=str(DEFAULT_DATABASE_PATH), help="SQLite database path")
    return launch(parser.parse_args(argv).db)
