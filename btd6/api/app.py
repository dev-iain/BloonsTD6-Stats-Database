from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from btd6.api.params import (
    form_to_filters,
    form_to_recommend_options,
    form_to_search_options,
)
from btd6.db import connect
from btd6.game_state import (
    GameStateError,
    NoGameStateError,
    load_game_state,
    parse_game_state,
    save_game_state,
    state_summary,
)
from btd6.income import NoIncomeDataError, cumulative_income, round_income
from btd6.query import QueryError, search_upgrades
from btd6.ranking import rank_upgrades
from btd6.recommend import recommend
from btd6.rounds import NoRoundDataError, get_round, get_round_summary, round_composition
from btd6.threats import round_threats

MISSING_DATABASE_MESSAGE = 'Database not found at {path}. Run "python -m btd6 load" first.'
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DEFAULT_STATE_PATH = PROJECT_ROOT / "game_state.json"
NOT_AN_OBJECT_MESSAGE = "Game state must be a JSON object"
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


def recommendation_rows(database_path: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    options = form_to_recommend_options(params)

    def work(connection: sqlite3.Connection) -> list[dict[str, Any]]:
        results = recommend(
            connection,
            options.round_number,
            options.money,
            options.difficulty,
            options.limit,
            options.horizon,
            options.owned,
            options.one_per_tower,
        )
        return [asdict(result) for result in results]

    return run_query(database_path, work)


def damage_type_names(database_path: str) -> list[str]:
    def work(connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute("SELECT name FROM damage_types ORDER BY name").fetchall()
        return [row[0] for row in rows]

    return run_query(database_path, work)


def round_income_payload(
    connection: sqlite3.Connection, round_number: int
) -> dict[str, Any] | None:
    try:
        income = round_income(connection, round_number)
        cumulative = cumulative_income(connection, round_number)
    except NoIncomeDataError:
        return None
    return {**asdict(income), "cumulative": cumulative}


def round_detail(database_path: str, round_number: int) -> dict[str, Any]:
    def work(connection: sqlite3.Connection) -> dict[str, Any]:
        try:
            groups = get_round(connection, round_number)
        except NoRoundDataError:
            raise
        except ValueError as error:
            raise QueryError(str(error)) from error
        summary = asdict(get_round_summary(connection, round_number))
        return {
            "round": round_number,
            "summary": summary,
            "composition": [asdict(total) for total in round_composition(groups)],
            "groups": [asdict(group) for group in groups],
            "income": round_income_payload(connection, round_number),
            "threats": asdict(round_threats(connection, round_number)),
        }

    return run_query(database_path, work)


def loaded_round_range(database_path: str) -> dict[str, int | None]:
    def work(connection: sqlite3.Connection) -> dict[str, int | None]:
        first, last = connection.execute("SELECT MIN(round), MAX(round) FROM rounds").fetchone()
        return {"first": first, "last": last}

    return run_query(database_path, work)


def utc_now() -> datetime:
    return datetime.now(UTC)


def decode_state_body(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise GameStateError(NOT_AN_OBJECT_MESSAGE) from error
    if not isinstance(payload, dict):
        raise GameStateError(NOT_AN_OBJECT_MESSAGE)
    return payload


def receive_game_state(
    state_path: Path, body: bytes, clock: Callable[[], datetime]
) -> dict[str, Any]:
    state = parse_game_state(decode_state_body(body))
    received_at = clock()
    save_game_state(state_path, state, received_at)
    return summarize_stored(state_path, received_at)


def summarize_stored(state_path: Path, current_time: datetime) -> dict[str, Any]:
    return state_summary(load_game_state(state_path, max_age_seconds=None), current_time)


def register_game_state_errors(app: FastAPI) -> None:
    @app.exception_handler(GameStateError)
    async def game_state_error(request: Request, error: GameStateError) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=422)

    @app.exception_handler(NoGameStateError)
    async def no_game_state(request: Request, error: NoGameStateError) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=404)


def register_game_state_routes(
    app: FastAPI, state_path: Path, clock: Callable[[], datetime]
) -> None:
    @app.post("/api/game-state")
    async def post_game_state(request: Request) -> dict[str, Any]:
        return receive_game_state(state_path, await request.body(), clock)

    @app.get("/api/game-state")
    def get_game_state() -> dict[str, Any]:
        return summarize_stored(state_path, clock())


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(QueryError)
    async def query_error(request: Request, error: QueryError) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=422)

    @app.exception_handler(NoRoundDataError)
    async def no_round_data(request: Request, error: NoRoundDataError) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=404)

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

    @app.get("/api/recommendations")
    def recommendations(request: Request) -> dict[str, Any]:
        params = {**request.query_params, "owned": request.query_params.getlist("owned")}
        return {"rows": recommendation_rows(database_path, params)}

    @app.get("/api/damage-types")
    def damage_types() -> dict[str, list[str]]:
        return {"damage_types": damage_type_names(database_path)}

    @app.get("/api/rounds")
    def rounds() -> dict[str, int | None]:
        return loaded_round_range(database_path)

    @app.get("/api/rounds/{round_number}")
    def round_by_number(round_number: int) -> dict[str, Any]:
        return round_detail(database_path, round_number)


def register_frontend(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


def create_app(
    database_path: str | Path,
    state_path: str | Path | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    app = FastAPI(title="BTD6 Tower Stats")
    register_error_handlers(app)
    register_game_state_errors(app)
    register_routes(app, str(database_path))
    register_game_state_routes(app, Path(state_path or DEFAULT_STATE_PATH), clock or utc_now)
    register_frontend(app)
    return app
