from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import uvicorn

from btd6.cli import build_parser, main


@pytest.fixture
def uvicorn_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def spy(app: object, **kwargs: Any) -> None:
        calls.append({"app": app, **kwargs})

    monkeypatch.setattr(uvicorn, "run", spy)
    return calls


def test_parser_knows_serve_with_defaults() -> None:
    args = build_parser().parse_args(["serve"])
    assert (args.command, args.host, args.port) == ("serve", "127.0.0.1", 8000)


def test_serve_runs_uvicorn_on_requested_address(
    tmp_path: Path, uvicorn_calls: list[dict[str, Any]]
) -> None:
    database = tmp_path / "btd6.db"
    database.touch()
    code = main(["--db", str(database), "serve", "--host", "0.0.0.0", "--port", "9100"])
    assert code == 0
    assert (uvicorn_calls[0]["host"], uvicorn_calls[0]["port"]) == ("0.0.0.0", 9100)


def test_serve_without_database_fails_before_starting(
    tmp_path: Path, uvicorn_calls: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "absent.db"
    code = main(["--db", str(missing), "serve"])
    captured = capsys.readouterr()
    assert code == 1
    assert uvicorn_calls == []
    assert captured.out == ""
    assert captured.err.strip() == (
        f'Database not found at {missing}. Run "python -m btd6 load" first.'
    )


def test_serve_passes_state_file_to_app(
    tmp_path: Path, uvicorn_calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    import btd6.api

    database = tmp_path / "btd6.db"
    database.touch()
    state_file = tmp_path / "live.json"
    created: list[tuple[str, str]] = []

    def fake_create_app(database_path: str, state_path: str) -> str:
        created.append((database_path, state_path))
        return "app"

    monkeypatch.setattr(btd6.api, "create_app", fake_create_app)
    code = main(["--db", str(database), "--state-file", str(state_file), "serve"])

    assert code == 0
    assert created == [(str(database), str(state_file))]
