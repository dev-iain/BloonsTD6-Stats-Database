from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import accumulate
from pathlib import Path

import pandas as pd
import requests

from btd6 import launcher
from btd6.agent.client import (
    API_KEY_FILES,
    KEY_FILE_NAME,
    AgentError,
    MissingApiKeyError,
    client_from_environment,
    write_key_file_template,
)
from btd6.agent.loop import run_agent
from btd6.costs import DIFFICULTY_MULTIPLIERS
from btd6.db import connect
from btd6.etl.fetch import (
    PROJECT_ROOT,
    fetch_bloons,
    fetch_income_set,
    fetch_roundset,
    fetch_tower_module,
)
from btd6.etl.pipeline import (
    INCOME_KEY,
    ROUND_GROUPS_KEY,
    ROUND_KEYS,
    ROUNDS_KEY,
    RefreshError,
    refresh_database,
)
from btd6.etl.towers import KNOWN_TOWERS
from btd6.formatting import (
    EMPTY_RESULTS_MESSAGE,
    RESULT_COLUMNS,
    format_amount,
    format_cell,
    income_summary,
)
from btd6.game_state import (
    DEFAULT_MAX_AGE_SECONDS,
    GameState,
    GameStateError,
    fake_game_state,
    load_game_state,
    parse_tower_spec,
    save_game_state,
)
from btd6.income import NoIncomeDataError, round_income, round_incomes
from btd6.query import POP_PROPERTIES, SORT_COLUMNS, QueryError, UpgradeFilters, search_upgrades
from btd6.ranking import rank_upgrades
from btd6.recommend import DEFAULT_HORIZON, OwnedTower, Recommendation, recommend
from btd6.rounds import NoRoundDataError, RoundGroup, get_round
from btd6.threats import RoundThreats, round_threats

KEY_FILE_PATH = PROJECT_ROOT / KEY_FILE_NAME
RANK_METRICS: dict[str, str] = {
    "dps": "dps",
    "dollar": "damage_per_dollar",
    "pierce-dollar": "pierce_damage_per_dollar",
    "moab-dps": "moab_dps",
}
RANK_COLUMNS: dict[str, str] = {
    "tower_name": "tower",
    "path": "path",
    "total_cost": "cost",
    "dps": "DPS",
    "moab_dps": "MOAB DPS",
    "damage_per_dollar": "damage per dollar",
}
MISSING_DATA_MESSAGE = 'No {kind} data loaded. Run "python -m btd6 load" first.'
DIFFICULTY_CHOICES = tuple(DIFFICULTY_MULTIPLIERS)
NO_RECOMMENDATION_MESSAGE = "No affordable upgrade can handle this round."
LIVE_COMMANDS = ("recommend", "agent")
LIVE_CONFLICT_MESSAGE = "--live cannot be combined with --round, --money or --difficulty"
MISSING_TARGET_MESSAGE = "the following arguments are required: --round, --money (or use --live)"


@dataclass(frozen=True)
class Target:
    round_number: int
    money: int
    difficulty: str
    live_state: GameState | None


def format_results(rows: list[sqlite3.Row]) -> str:
    if not rows:
        return EMPTY_RESULTS_MESSAGE
    records = [
        {
            header: format_cell(column, result_row[column])
            for column, header in RESULT_COLUMNS.items()
        }
        for result_row in rows
    ]
    with pd.option_context("display.max_rows", None, "display.max_columns", None):
        return pd.DataFrame(records).to_string(index=False)


def format_float(value: float) -> str:
    rounded = round(value, 4)
    return str(int(rounded)) if rounded.is_integer() else str(rounded)


def format_rank_value(value: object) -> str:
    if value is None or pd.isna(value):
        return "-"
    return format_float(float(value))


def format_ranking(frame: pd.DataFrame) -> str:
    if frame.empty:
        return EMPTY_RESULTS_MESSAGE
    table = pd.DataFrame({"rank": range(1, len(frame) + 1)})
    for column, header in RANK_COLUMNS.items():
        values = frame[column].tolist()
        if column in ("tower_name", "path"):
            table[header] = values
        else:
            table[header] = [format_rank_value(value) for value in values]
    with pd.option_context("display.max_rows", None, "display.max_columns", None):
        return table.to_string(index=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="btd6")
    parser.add_argument("--db", default=str(PROJECT_ROOT / "btd6.db"), help="SQLite database path")
    parser.add_argument(
        "--state-file",
        default=str(PROJECT_ROOT / "game_state.json"),
        help="live game state file path",
    )
    parser.add_argument("--debug", action="store_true", help="print tracebacks for errors")
    subparsers = parser.add_subparsers(dest="command")
    load_parser = subparsers.add_parser("load", help="load resolved tower data into the database")
    add_load_options(load_parser)
    search_parser = subparsers.add_parser("search", help="search towers and upgrades by stats")
    add_search_options(search_parser)
    rank_parser = subparsers.add_parser("rank", help="rank upgrades by damage per second or dollar")
    add_rank_options(rank_parser)
    serve_parser = subparsers.add_parser("serve", help="serve the web interface and API")
    add_serve_options(serve_parser)
    start_parser = subparsers.add_parser(
        "start", help="build the database if needed, then serve and open the web UI"
    )
    add_start_options(start_parser)
    rounds_parser = subparsers.add_parser("rounds", help="show the bloons in a round or range")
    add_rounds_options(rounds_parser)
    income_parser = subparsers.add_parser("income", help="show income from popping bloons")
    add_income_options(income_parser)
    recommend_parser = subparsers.add_parser(
        "recommend", help="recommend affordable upgrades for a round"
    )
    add_recommend_options(recommend_parser)
    agent_parser = subparsers.add_parser("agent", help="ask the LLM advisor what to buy")
    add_agent_options(agent_parser)
    add_state_subparsers(subparsers)
    return parser


def add_state_subparsers(subparsers: argparse._SubParsersAction) -> None:
    fake_parser = subparsers.add_parser("fake-state", help="write a fake game state file")
    add_fake_state_options(fake_parser)
    state_parser = subparsers.add_parser("game-state", help="show the stored game state")
    state_parser.add_argument("--max-age", type=float, default=DEFAULT_MAX_AGE_SECONDS)


def add_fake_state_options(subparser: argparse.ArgumentParser) -> None:
    add_round_money_options(subparser)
    subparser.add_argument("--tower", action="append", metavar="NAME:X-Y-Z")


def add_round_money_options(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--round", type=int, dest="round_number", required=True, metavar="N")
    subparser.add_argument("--money", type=int, required=True)
    subparser.add_argument("--difficulty", choices=DIFFICULTY_CHOICES, default="medium")


def add_target_options(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--round", type=int, dest="round_number", metavar="N")
    subparser.add_argument("--money", type=int)
    subparser.add_argument("--difficulty", choices=DIFFICULTY_CHOICES, help="default medium")
    subparser.add_argument(
        "--live", action="store_true", help="read round, money and difficulty from the live game"
    )
    subparser.add_argument(
        "--max-age",
        type=float,
        default=DEFAULT_MAX_AGE_SECONDS,
        help="with --live, oldest accepted state in seconds (0 turns the check off)",
    )


def add_agent_options(subparser: argparse.ArgumentParser) -> None:
    add_target_options(subparser)
    subparser.add_argument("--max-iterations", type=int, default=8)


def add_recommend_options(subparser: argparse.ArgumentParser) -> None:
    add_target_options(subparser)
    subparser.add_argument("--limit", type=int)
    subparser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    subparser.add_argument("--one-per-tower", action="store_true")


def add_income_options(subparser: argparse.ArgumentParser) -> None:
    group = subparser.add_mutually_exclusive_group(required=True)
    group.add_argument("--round", type=int, dest="round_number", metavar="N")
    group.add_argument("--up-to", type=int, dest="up_to_round", metavar="N")


def add_serve_options(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--host", default="127.0.0.1")
    subparser.add_argument("--port", type=int, default=8000)


def add_start_options(subparser: argparse.ArgumentParser) -> None:
    add_serve_options(subparser)
    subparser.add_argument(
        "--refresh", action="store_true", help="reload the data from the wiki first"
    )
    subparser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    subparser.add_argument("--game", action="store_true", help="launch BTD6 through Steam")
    subparser.set_defaults(tower=None, no_rounds=False)


def add_load_options(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--tower", action="append", choices=KNOWN_TOWERS, metavar="NAME")
    subparser.add_argument(
        "--no-rounds", action="store_true", help="skip loading bloons and rounds"
    )


def add_rounds_options(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--round", type=int, dest="round_number", metavar="N")
    subparser.add_argument("--from", type=int, dest="first_round", metavar="A")
    subparser.add_argument("--to", type=int, dest="last_round", metavar="B")
    subparser.set_defaults(rounds_parser=subparser)


def add_filter_options(subparser: argparse.ArgumentParser) -> None:
    for flag in ("--can-pop", "--cannot-pop"):
        subparser.add_argument(flag, action="append", choices=POP_PROPERTIES, metavar="PROP")
    for flag in ("--min-pierce", "--min-damage", "--min-range", "--min-speed"):
        subparser.add_argument(flag, type=float)
    subparser.add_argument("--tower", choices=KNOWN_TOWERS, metavar="NAME")
    subparser.add_argument("--damage-type")
    subparser.add_argument("--camo", action=argparse.BooleanOptionalAction, default=None)
    subparser.add_argument("--limit", type=int)


def add_search_options(subparser: argparse.ArgumentParser) -> None:
    add_filter_options(subparser)
    subparser.add_argument("--sort", choices=SORT_COLUMNS)


def add_rank_options(subparser: argparse.ArgumentParser) -> None:
    add_filter_options(subparser)
    subparser.add_argument("--metric", choices=list(RANK_METRICS), default="dollar")
    subparser.add_argument("--difficulty", choices=DIFFICULTY_CHOICES, default="medium")


def build_filters(args: argparse.Namespace) -> UpgradeFilters:
    pop_flags = {f"can_pop_{prop}": True for prop in args.can_pop or []}
    pop_flags.update({f"can_pop_{prop}": False for prop in args.cannot_pop or []})
    return UpgradeFilters(
        tower_name=args.tower,
        min_pierce=args.min_pierce,
        min_damage=args.min_damage,
        min_range=args.min_range,
        min_projectile_speed=args.min_speed,
        damage_type=args.damage_type,
        can_hit_camo=args.camo,
        **pop_flags,
    )


def print_loaded(loaded: dict[str, int]) -> None:
    for tower_name, upgrade_count in loaded.items():
        if tower_name not in (*ROUND_KEYS, INCOME_KEY):
            print(f"{tower_name}: {upgrade_count} upgrades")
    if INCOME_KEY in loaded:
        print(f"Income: {loaded[INCOME_KEY]} multiplier thresholds")
    if ROUNDS_KEY in loaded and ROUND_GROUPS_KEY in loaded:
        print(f"Rounds: {loaded[ROUNDS_KEY]} rounds, {loaded[ROUND_GROUPS_KEY]} groups")


def report_refresh_error(error: RefreshError) -> int:
    for failure in error.failures.values():
        if isinstance(failure, requests.ConnectionError):
            print(f"Could not reach the wiki: {failure}", file=sys.stderr)
            return 1
    print_loaded(error.loaded)
    for tower_name, failure in error.failures.items():
        print(f"{tower_name}: failed: {failure}", file=sys.stderr)
    return 1


def run_load(args: argparse.Namespace) -> int:
    connection = connect(args.db)
    try:
        loaded = refresh_database(
            connection,
            args.tower,
            fetch=fetch_tower_module,
            include_rounds=not args.no_rounds,
            fetch_bloon_rows=fetch_bloons,
            fetch_roundset=fetch_roundset,
            fetch_income_set=fetch_income_set,
        )
    except RefreshError as error:
        return report_refresh_error(error)
    finally:
        connection.close()
    print_loaded(loaded)
    return 0


def check_request(args: argparse.Namespace) -> int | None:
    conflicts = set(args.can_pop or []) & set(args.cannot_pop or [])
    if conflicts:
        conflict = next(prop for prop in POP_PROPERTIES if prop in conflicts)
        print(f"--can-pop and --cannot-pop both list {conflict}", file=sys.stderr)
        return 2
    return check_database_exists(args)


def check_database_exists(args: argparse.Namespace) -> int | None:
    if not Path(args.db).exists():
        print(f'Database not found at {args.db}. Run "python -m btd6 load" first.', file=sys.stderr)
        return 1
    return None


def warn_if_attacks_missing(connection: sqlite3.Connection) -> None:
    has_upgrades = connection.execute("SELECT 1 FROM upgrades LIMIT 1").fetchone()
    has_attacks = connection.execute("SELECT 1 FROM attacks LIMIT 1").fetchone()
    if has_upgrades and not has_attacks:
        print(
            'No attack data stored, so DPS is empty. Run "python -m btd6 load" to fill it.',
            file=sys.stderr,
        )


def run_rank(args: argparse.Namespace) -> int:
    failure = check_request(args)
    if failure is not None:
        return failure
    connection = connect(args.db)
    try:
        warn_if_attacks_missing(connection)
        frame = rank_upgrades(
            connection,
            build_filters(args),
            metric=RANK_METRICS[args.metric],
            difficulty=args.difficulty,
            limit=args.limit,
        )
        print(format_ranking(frame))
    finally:
        connection.close()
    return 0


def run_search(args: argparse.Namespace) -> int:
    failure = check_request(args)
    if failure is not None:
        return failure
    connection = connect(args.db)
    try:
        rows = search_upgrades(connection, build_filters(args), sort_by=args.sort, limit=args.limit)
        print(format_results(rows))
    finally:
        connection.close()
    return 0


def check_rounds_selection(args: argparse.Namespace) -> None:
    has_range = args.first_round is not None or args.last_round is not None
    if args.round_number is not None and has_range:
        args.rounds_parser.error("--round cannot be combined with --from/--to")
    if args.round_number is None and not has_range:
        args.rounds_parser.error("one of --round or --from/--to is required")
    if has_range and (args.first_round is None or args.last_round is None):
        args.rounds_parser.error("--from and --to must be given together")


def format_rounds(groups_by_round: dict[int, list[RoundGroup]]) -> str:
    records = [
        {
            "round": number,
            "bloon": group.bloon,
            "count": group.count,
            "camo": format_cell("can_hit_camo", group.is_camo),
            "regrow": format_cell("can_hit_camo", group.is_regrow),
            "fortified": format_cell("can_hit_camo", group.is_fortified),
            "start": format_cell("start", group.start),
            "duration": format_cell("duration", group.duration),
            "rbe": format_cell("rbe", group.rbe),
        }
        for number, groups in groups_by_round.items()
        for group in groups
    ]
    with pd.option_context("display.max_rows", None, "display.max_columns", None):
        return pd.DataFrame(records).to_string(index=False)


def load_rounds_table(connection: sqlite3.Connection, args: argparse.Namespace) -> str:
    first = args.round_number if args.round_number is not None else args.first_round
    last = args.round_number if args.round_number is not None else args.last_round
    if first > last:
        raise ValueError("--from must not be greater than --to")
    return format_rounds(
        {number: get_round(connection, number) for number in range(first, last + 1)}
    )


def format_threats(threats: RoundThreats) -> str:
    lines = [
        f"Threats (round {threats.round})",
        f"total RBE: {threats.total_rbe}",
        f"unknown groups: {threats.unknown_groups}",
        *(f"{name}: {share:.1%}" for name, share in threats.property_share.items()),
        f"camo: {threats.camo_share:.1%}",
        f"regrow: {threats.regrow_share:.1%}",
        f"moab: {threats.moab_share:.1%}",
        f"mean layers: {threats.mean_layers:.2f}",
    ]
    return "\n".join(lines)


def report_missing_data(error: NoRoundDataError | NoIncomeDataError) -> int:
    kind = "income" if isinstance(error, NoIncomeDataError) else "round"
    print(MISSING_DATA_MESSAGE.format(kind=kind), file=sys.stderr)
    return 1


def run_rounds(args: argparse.Namespace) -> int:
    check_rounds_selection(args)
    failure = check_database_exists(args)
    if failure is not None:
        return failure
    connection = connect(args.db)
    try:
        table = load_rounds_table(connection, args)
        if args.round_number is not None:
            table += "\n\n" + format_threats(round_threats(connection, args.round_number))
    except NoRoundDataError as error:
        return report_missing_data(error)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    finally:
        connection.close()
    print(table)
    return 0


def format_income_table(connection: sqlite3.Connection, up_to_round: int) -> str:
    incomes = round_incomes(connection, up_to_round)
    running_totals = accumulate(income.total for income in incomes)
    records = [
        {
            "round": number,
            "pop cash": format_amount(income.pop_cash),
            "end bonus": format_amount(income.end_bonus),
            "total": format_amount(income.total),
            "running total": format_amount(running),
        }
        for number, income, running in zip(
            range(1, up_to_round + 1), incomes, running_totals, strict=True
        )
    ]
    with pd.option_context("display.max_rows", None, "display.max_columns", None):
        return pd.DataFrame(records).to_string(index=False)


def build_income_output(connection: sqlite3.Connection, args: argparse.Namespace) -> str:
    if args.round_number is not None:
        income = round_income(connection, args.round_number)
        return income_summary(income, args.round_number)
    return format_income_table(connection, args.up_to_round)


def run_income(args: argparse.Namespace) -> int:
    failure = check_database_exists(args)
    if failure is not None:
        return failure
    connection = connect(args.db)
    try:
        output = build_income_output(connection, args)
    except (NoRoundDataError, NoIncomeDataError) as error:
        return report_missing_data(error)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    finally:
        connection.close()
    print(output)
    return 0


def format_recommendations(results: list[Recommendation]) -> str:
    if not results:
        return NO_RECOMMENDATION_MESSAGE
    table = pd.DataFrame(
        {
            "rank": range(1, len(results) + 1),
            "tower": [result.tower_name for result in results],
            "path": [result.path for result in results],
            "upgrade from": [result.upgrade_from or "" for result in results],
            "cost": [format_rank_value(result.total_cost) for result in results],
            "score": [format_rank_value(result.score) for result in results],
            "leaks at": [
                "" if result.first_leak_round is None else str(result.first_leak_round)
                for result in results
            ],
            "reasons": [", ".join(result.reasons) for result in results],
        }
    )
    with pd.option_context("display.max_rows", None, "display.max_columns", None):
        return table.to_string(index=False)


def check_target_options(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    manual_values = (args.round_number, args.money, args.difficulty)
    if args.live and any(value is not None for value in manual_values):
        parser.error(LIVE_CONFLICT_MESSAGE)
    if not args.live and (args.round_number is None or args.money is None):
        parser.error(MISSING_TARGET_MESSAGE)


def resolve_target(args: argparse.Namespace) -> Target:
    if not args.live:
        return Target(args.round_number, args.money, args.difficulty or "medium", None)
    max_age = args.max_age if args.max_age > 0 else None
    state = load_game_state(Path(args.state_file), max_age).state
    return Target(state.round_number, state.money, state.difficulty, state)


def load_target(args: argparse.Namespace) -> Target | None:
    try:
        return resolve_target(args)
    except GameStateError as error:
        print(error, file=sys.stderr)
        return None


def live_line(target: Target) -> str:
    return (
        f"Live game: round {target.round_number}, ${target.money:,}, difficulty {target.difficulty}"
    )


def owned_from_target(target: Target) -> list[OwnedTower]:
    if target.live_state is None:
        return []
    return [
        OwnedTower(tower.tower_name, tower.path)
        for tower in target.live_state.towers
        if tower.known
    ]


def owned_line(owned: list[OwnedTower]) -> str:
    if not owned:
        return "Owned: none"
    return "Owned: " + ", ".join(f"{entry.tower_name} {entry.path}" for entry in owned)


def run_recommend(args: argparse.Namespace) -> int:
    failure = check_database_exists(args)
    if failure is not None:
        return failure
    target = load_target(args)
    if target is None:
        return 1
    owned = owned_from_target(target)
    connection = connect(args.db)
    try:
        results = recommend(
            connection,
            target.round_number,
            target.money,
            target.difficulty,
            args.limit,
            args.horizon,
            owned,
            args.one_per_tower,
        )
    except NoRoundDataError as error:
        return report_missing_data(error)
    finally:
        connection.close()
    if target.live_state is not None:
        print(live_line(target))
        print(owned_line(owned))
    print(format_recommendations(results))
    return 0


def agent_live_options(args: argparse.Namespace, target: Target) -> dict[str, object]:
    if target.live_state is None:
        return {}
    return {"state_path": Path(args.state_file), "owned_towers": target.live_state.towers}


def run_agent_command(args: argparse.Namespace) -> int:
    failure = check_database_exists(args)
    if failure is not None:
        return failure
    target = load_target(args)
    if target is None:
        return 1
    try:
        client = client_from_environment(os.environ, API_KEY_FILES)
    except MissingApiKeyError as error:
        print(error, file=sys.stderr)
        return 2
    connection = connect(args.db)
    try:
        result = run_agent(
            connection,
            client,
            target.round_number,
            target.money,
            target.difficulty,
            args.max_iterations,
            **agent_live_options(args, target),
        )
    except AgentError as error:
        print(error, file=sys.stderr)
        return 1
    finally:
        connection.close()
    print(result.answer)
    return 0


def run_serve(args: argparse.Namespace, auto_stop: bool = False) -> int:
    if not Path(args.db).exists():
        print(f'Database not found at {args.db}. Run "python -m btd6 load" first.', file=sys.stderr)
        return 1
    import uvicorn

    from btd6.api import create_app

    app = create_app(args.db, state_path=args.state_file, auto_stop=auto_stop)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def build_database(args: argparse.Namespace) -> int:
    was_missing = not Path(args.db).exists()
    print("Building the database from the BTD6 wiki...")
    load_code = run_load(args)
    if load_code != 0 and was_missing:
        Path(args.db).unlink(missing_ok=True)
    return load_code


def run_start(args: argparse.Namespace) -> int:
    problem = launcher.replace_running_advisor(args.host, args.port)
    if problem is not None:
        print(problem, file=sys.stderr)
        return 1
    if args.refresh or not Path(args.db).exists():
        load_code = build_database(args)
        if load_code != 0:
            return load_code
    if write_key_file_template(KEY_FILE_PATH):
        print(f"Created {KEY_FILE_NAME}: paste a free Gemini API key there to use the agent.")
    if args.game:
        launcher.launch_game()
    url = launcher.browser_url(args.host, args.port)
    print(f"BTD6 advisor running at {url} (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        launcher.open_browser_when_ready(url, args.host, args.port)
    return run_serve(args, auto_stop=not args.no_browser)


def format_game_state(state: GameState) -> str:
    lines = [
        f"Round {state.round_number}",
        f"Money ${state.money:,}",
        f"Lives {state.lives}",
        f"Difficulty {state.difficulty}",
        f"Mode {state.mode}",
        f"Map {state.map_name}",
        f"Towers ({len(state.towers)})",
        *(f"  {tower.tower_name or tower.base_id} {tower.path}" for tower in state.towers),
    ]
    return "\n".join(lines)


def run_fake_state(args: argparse.Namespace) -> int:
    path = Path(args.state_file)
    try:
        specs = [parse_tower_spec(spec) for spec in args.tower or []]
        state = fake_game_state(args.round_number, args.money, args.difficulty, specs)
    except GameStateError as error:
        print(error, file=sys.stderr)
        return 2
    save_game_state(path, state, datetime.now(UTC))
    print(f"Saved round {state.round_number}, ${state.money:,} to {path}")
    return 0


def run_game_state(args: argparse.Namespace) -> int:
    max_age = args.max_age if args.max_age > 0 else None
    try:
        stored = load_game_state(Path(args.state_file), max_age)
    except GameStateError as error:
        print(error, file=sys.stderr)
        return 1
    print(format_game_state(stored.state))
    return 0


HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "load": run_load,
    "search": run_search,
    "rank": run_rank,
    "serve": run_serve,
    "start": run_start,
    "rounds": run_rounds,
    "income": run_income,
    "recommend": run_recommend,
    "agent": run_agent_command,
    "fake-state": run_fake_state,
    "game-state": run_game_state,
}


def run_guarded(handler: Callable[[argparse.Namespace], int], args: argparse.Namespace) -> int:
    try:
        return handler(args)
    except QueryError as error:
        print(error, file=sys.stderr)
        return 2
    except Exception as error:
        if args.debug:
            traceback.print_exc()
        print(f"Unexpected error: {error}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return 2
    if args.command in LIVE_COMMANDS:
        check_target_options(parser, args)
    return run_guarded(HANDLERS[args.command], args)
