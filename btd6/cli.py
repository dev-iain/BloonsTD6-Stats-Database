from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from btd6.etl.fetch import PROJECT_ROOT


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
