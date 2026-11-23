from __future__ import annotations

import argparse
import sqlite3
import sys
import traceback
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import requests

from btd6.costs import DIFFICULTY_MULTIPLIERS
from btd6.db import connect
from btd6.etl.fetch import PROJECT_ROOT, fetch_tower_module
from btd6.etl.pipeline import RefreshError, refresh_database
from btd6.etl.towers import MAGIC_TOWERS
from btd6.formatting import EMPTY_RESULTS_MESSAGE, RESULT_COLUMNS, format_cell
from btd6.query import POP_PROPERTIES, SORT_COLUMNS, QueryError, UpgradeFilters, search_upgrades
from btd6.ranking import METRICS, rank_upgrades

RANK_METRICS: dict[str, str] = dict(zip(("dps", "dollar", "pierce-dollar"), METRICS, strict=True))
RANK_COLUMNS: dict[str, str] = {
    "tower_name": "tower",
    "path": "path",
    "total_cost": "cost",
    "dps": "DPS",
    "damage_per_dollar": "damage per dollar",
}
DIFFICULTY_CHOICES = tuple(DIFFICULTY_MULTIPLIERS)


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
    parser.add_argument("--debug", action="store_true", help="print tracebacks for errors")
    subparsers = parser.add_subparsers(dest="command")
    load_parser = subparsers.add_parser("load", help="load resolved tower data into the database")
    add_load_options(load_parser)
    search_parser = subparsers.add_parser("search", help="search towers and upgrades by stats")
    add_search_options(search_parser)
    rank_parser = subparsers.add_parser("rank", help="rank upgrades by damage per second or dollar")
    add_rank_options(rank_parser)
    subparsers.add_parser("gui", aliases=["ui"], help="open the desktop interface")
    return parser


def add_load_options(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--tower", action="append", choices=MAGIC_TOWERS, metavar="NAME")


def add_filter_options(subparser: argparse.ArgumentParser) -> None:
    for flag in ("--can-pop", "--cannot-pop"):
        subparser.add_argument(flag, action="append", choices=POP_PROPERTIES, metavar="PROP")
    for flag in ("--min-pierce", "--min-damage", "--min-range", "--min-speed"):
        subparser.add_argument(flag, type=float)
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
        category="Magic",
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
        print(f"{tower_name}: {upgrade_count} upgrades")


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
        loaded = refresh_database(connection, args.tower, fetch=fetch_tower_module)
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
    if not Path(args.db).exists():
        print(f'Database not found at {args.db}. Run "python -m btd6 load" first.', file=sys.stderr)
        return 1
    return None


def run_rank(args: argparse.Namespace) -> int:
    failure = check_request(args)
    if failure is not None:
        return failure
    connection = connect(args.db)
    try:
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


def run_gui(args: argparse.Namespace) -> int:
    from btd6.ui.launcher import launch

    return launch(args.db)


HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "load": run_load,
    "search": run_search,
    "rank": run_rank,
    "gui": run_gui,
    "ui": run_gui,
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
    return run_guarded(HANDLERS[args.command], args)
