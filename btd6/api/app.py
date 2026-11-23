from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from btd6.api.params import form_to_filters, form_to_search_options
from btd6.db import connect
from btd6.query import QueryError, search_upgrades
from btd6.ranking import rank_upgrades

MISSING_DATABASE_MESSAGE = 'Database not found at {path}. Run "python -m btd6 load" first.'
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
DEFAULT_RANK_METRIC = "damage_per_dollar"
DEFAULT_DIFFICULTY = "medium"


class DatabaseMissingError(RuntimeError):
    """The configured database file does not exist."""


def run_query[Result](database_path: str, work: Callable[[sqlite3.Connection], Result]) -> Result:
    if database_path != ":memory:" and not Path(database_path).exists():
        raise DatabaseMissingError(MISSING_DATABASE_MESSAGE.format(path=database_path))
    connection = connect(database_path)
    try:
        return work(connection)
    finally:
        connection.close()


def frame_to_records(frame: pandas.DataFrame) -> list[dict[str, Any]]:
    cleaned = frame.astype(object).where(frame.notna(), None)
    return cleaned.to_dict("records")


def upgrade_rows(database_path: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    filters = form_to_filters(params)
    sort_by, limit = form_to_search_options(params)

    def work(connection: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = search_upgrades(connection, filters, sort_by=sort_by, limit=limit)
        return [dict(row) for row in rows]

    return run_query(database_path, work)


def ranking_rows(database_path: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    filters = form_to_filters(params)
    _, limit = form_to_search_options(params)
    metric = params.get("metric", DEFAULT_RANK_METRIC)
    difficulty = params.get("difficulty", DEFAULT_DIFFICULTY)

    def work(connection: sqlite3.Connection) -> list[dict[str, Any]]:
        frame = rank_upgrades(connection, filters, metric, difficulty, limit)
        return frame_to_records(frame)

    return run_query(database_path, work)


def damage_type_names(database_path: str) -> list[str]:
    def work(connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute("SELECT name FROM damage_types ORDER BY name").fetchall()
        return [row[0] for row in rows]

    return run_query(database_path, work)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(QueryError)
    async def query_error(request: Request, error: QueryError) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=422)

    @app.exception_handler(DatabaseMissingError)
    async def missing_database(request: Request, error: DatabaseMissingError) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=503)


def register_routes(app: FastAPI, database_path: str) -> None:
    @app.get("/api/upgrades")
    def upgrades(request: Request) -> dict[str, Any]:
        return {"rows": upgrade_rows(database_path, request.query_params)}

    @app.get("/api/rankings")
    def rankings(request: Request) -> dict[str, Any]:
        return {"rows": ranking_rows(database_path, request.query_params)}

    @app.get("/api/damage-types")
    def damage_types() -> dict[str, list[str]]:
        return {"damage_types": damage_type_names(database_path)}


def register_frontend(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


def create_app(database_path: str | Path) -> FastAPI:
    app = FastAPI(title="BTD6 Tower Stats")
    register_error_handlers(app)
    register_routes(app, str(database_path))
    register_frontend(app)
    return app
