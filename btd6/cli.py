from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Callable

import pandas as pd

from btd6.etl.fetch import PROJECT_ROOT

RESULT_COLUMNS: dict[str, str] = {
    "tower_name": "tower",
    "path": "path",
    "damage_type": "type",
    "projectile_damage": "damage",
    "projectile_pierce": "pierce",
    "range": "range",
    "projectile_speed": "speed",
    "attack_rate": "rate",
    "can_hit_camo": "camo",
    "can_pop_lead": "lead",
    "can_pop_black": "black",
    "can_pop_white": "white",
    "can_pop_purple": "purple",
    "can_pop_glass": "glass",
    "can_pop_frozen": "frozen",
}
FLAG_COLUMNS = frozenset(
    name for name in RESULT_COLUMNS if name.startswith(("can_pop_", "can_hit_"))
)
EMPTY_RESULTS_MESSAGE = "No upgrades match these filters."


def format_cell(column: str, value: object) -> str:
    if value is None:
        return "-"
    if column in FLAG_COLUMNS:
        return "yes" if value else "no"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="btd6")
    parser.add_argument("--db", default=str(PROJECT_ROOT / "btd6.db"), help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("load", help="load resolved tower data into the database")
    subparsers.add_parser("search", help="search towers and upgrades by stats")
    return parser


def run_load(args: argparse.Namespace) -> int:
    print("load: not implemented", file=sys.stderr)
    return 1


def run_search(args: argparse.Namespace) -> int:
    print("search: not implemented", file=sys.stderr)
    return 1


HANDLERS: dict[str, Callable[[argparse.Namespace], int]] = {
    "load": run_load,
    "search": run_search,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return 2
    return HANDLERS[args.command](args)
