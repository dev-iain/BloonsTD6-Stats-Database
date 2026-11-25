from __future__ import annotations

import asyncio
import json
import os
import secrets
import signal
import sqlite3
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import pandas
from fastapi import BackgroundTasks, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from btd6.agent.client import (
    API_KEY_FILES,
    AgentError,
    MissingApiKeyError,
    OpenAICompatibleClient,
    client_from_environment,
)
from btd6.agent.loop import DEFAULT_MAX_ITERATIONS, run_agent
from btd6.agent.picks import AgentResult
from btd6.api.params import (
    form_to_filters,
    form_to_recommend_options,
    form_to_search_options,
    parse_minimum,
    parse_required_int,
)
from btd6.api.presence import HEARTBEAT_SECONDS, PagePresence, watch_presence
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
PRESENCE_EVENTS = ("heartbeat", "closing")
QUIT_HEADER_MESSAGE = "Missing X-BTD6-Action: quit header"


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
    max_cost = parse_minimum("money", str(params.get("money", "")))

    def work(connection: sqlite3.Connection) -> list[dict[str, Any]]:
        frame = rank_upgrades(connection, filters, metric, difficulty, limit, max_cost)
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


def default_agent_client() -> OpenAICompatibleClient:
    return client_from_environment(os.environ, API_KEY_FILES)


def parse_max_iterations(params: Mapping[str, Any]) -> int:
    if not str(params.get("max_iterations") or "").strip():
        return DEFAULT_MAX_ITERATIONS
    return parse_required_int("max_iterations", params.get("max_iterations"))


def live_agent_options(
    params: Mapping[str, Any], state_path: Path, clock: Callable[[], datetime]
) -> dict[str, Any]:
    if str(params.get("live", "")).lower() != "true":
        return {}
    stored = load_game_state(state_path, now=clock())
    return {"state_path": state_path, "owned_towers": stored.state.towers}


def agent_result_payload(result: AgentResult) -> dict[str, Any]:
    return {
        "answer": result.answer,
        "picks": [asdict(pick) for pick in result.picks],
        "tool_calls": [
            {"name": call.name, "arguments": call.arguments} for call in result.tool_calls
        ],
    }


def agent_payload(
    database_path: str,
    params: Mapping[str, Any],
    state_path: Path,
    clock: Callable[[], datetime],
    client_factory: Callable[[], Any],
) -> dict[str, Any]:
    options = form_to_recommend_options(params)
    max_iterations = parse_max_iterations(params)
    live_options = live_agent_options(params, state_path, clock)
    client = client_factory()

    def work(connection: sqlite3.Connection) -> dict[str, Any]:
        result = run_agent(
            connection,
            client,
            options.round_number,
            options.money,
            options.difficulty,
            max_iterations,
            **live_options,
        )
        return agent_result_payload(result)

    return run_query(database_path, work)


def register_agent_route(
    app: FastAPI,
    database_path: str,
    state_path: Path,
    clock: Callable[[], datetime],
    client_factory: Callable[[], Any],
) -> None:
    @app.get("/api/agent")
    def agent(request: Request) -> dict[str, Any]:
        return agent_payload(database_path, request.query_params, state_path, clock, client_factory)


def register_agent_errors(app: FastAPI) -> None:
    @app.exception_handler(AgentError)
    async def agent_error(request: Request, error: AgentError) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=502)

    @app.exception_handler(MissingApiKeyError)
    async def missing_key(request: Request, error: MissingApiKeyError) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=503)


def damage_type_names(database_path: str) -> list[str]:
    def work(connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute("SELECT name FROM damage_types ORDER BY name").fetchall()
        return [row[0] for row in rows]

    return run_query(database_path, work)


def tower_names(database_path: str) -> list[str]:
    def work(connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute("SELECT name FROM towers ORDER BY name").fetchall()
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
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"app": "btd6", "pid": os.getpid()}

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

    @app.get("/api/towers")
    def towers() -> dict[str, list[str]]:
        return {"towers": tower_names(database_path)}

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


def stop_server() -> None:
    signal.raise_signal(signal.SIGINT)


def parse_presence_event(body: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError, UnicodeDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def presence_problem(payload: dict[str, Any] | None, token: str) -> JSONResponse | None:
    if payload is not None and payload.get("token") != token:
        return JSONResponse({"error": "Bad session token"}, status_code=403)
    page = payload.get("page") if payload else None
    valid_page = isinstance(page, str) and page.strip()
    if not valid_page or payload.get("event") not in PRESENCE_EVENTS:
        return JSONResponse({"error": "Invalid presence event"}, status_code=422)
    return None


def register_session_routes(
    app: FastAPI,
    presence: PagePresence,
    clock: Callable[[], datetime],
    request_stop: Callable[[], None],
) -> None:
    @app.post("/api/shutdown")
    def shutdown(request: Request, tasks: BackgroundTasks) -> Response:
        if request.headers.get("X-BTD6-Action") != "quit":
            return JSONResponse({"error": QUIT_HEADER_MESSAGE}, status_code=403)
        tasks.add_task(request_stop)
        return JSONResponse({"stopping": True})

    @app.get("/api/session")
    def session() -> dict[str, Any]:
        return {
            "token": presence.token,
            "auto_stop": app.state.auto_stop,
            "heartbeat_seconds": HEARTBEAT_SECONDS,
        }

    @app.post("/api/presence")
    async def presence_event(request: Request) -> Response:
        payload = parse_presence_event(await request.body())
        problem = presence_problem(payload, presence.token)
        if problem is not None:
            return problem
        record = presence.heartbeat if payload["event"] == "heartbeat" else presence.closing
        record(payload["page"], clock())
        return Response(status_code=204)


def presence_lifespan(
    watch: Callable[[], Coroutine[Any, Any, None]] | None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        watcher = asyncio.create_task(watch()) if watch is not None else None
        yield
        if watcher is not None:
            watcher.cancel()

    return lifespan


def create_app(
    database_path: str | Path,
    state_path: str | Path | None = None,
    clock: Callable[[], datetime] | None = None,
    agent_client_factory: Callable[[], Any] | None = None,
    request_stop: Callable[[], None] | None = None,
    presence: PagePresence | None = None,
    auto_stop: bool = False,
    watch_interval: float = 1.0,
) -> FastAPI:
    resolved_clock = clock or utc_now
    stopper = request_stop or stop_server
    tracker = presence or PagePresence(secrets.token_urlsafe(16))
    watch = partial(watch_presence, tracker, resolved_clock, stopper, watch_interval)
    lifespan = presence_lifespan(watch if auto_stop else None)
    app = FastAPI(title="BTD6 Tower Stats", lifespan=lifespan)
    app.state.auto_stop = auto_stop
    register_error_handlers(app)
    register_game_state_errors(app)
    register_agent_errors(app)
    register_routes(app, str(database_path))
    resolved_state = Path(state_path or DEFAULT_STATE_PATH)
    register_game_state_routes(app, resolved_state, resolved_clock)
    register_session_routes(app, tracker, resolved_clock, stopper)
    factory = agent_client_factory or default_agent_client
    register_agent_route(app, str(database_path), resolved_state, resolved_clock, factory)
    register_frontend(app)
    return app
