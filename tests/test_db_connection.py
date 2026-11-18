from __future__ import annotations

from pathlib import Path

import btd6.db.connection as connection_module
from btd6.db import connect
from btd6.db.connection import DEFAULT_DATABASE_PATH
from btd6.etl.fetch import PROJECT_ROOT


def test_default_path_is_project_root_btd6_db():
    assert DEFAULT_DATABASE_PATH == PROJECT_ROOT / "btd6.db"


def test_connect_none_uses_default_path(tmp_path: Path, monkeypatch):
    target = tmp_path / "default.db"
    monkeypatch.setattr(connection_module, "DEFAULT_DATABASE_PATH", target)
    connection = connect()
    try:
        assert target.exists()
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()


def test_connect_reexported_from_package():
    assert connect is connection_module.connect
