from __future__ import annotations

import ast
import re
import sqlite3
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from btd6.query import QueryError, UpgradeFilters, search_upgrades
from tests.test_query import build_database

GOLDEN_CSV = Path(__file__).resolve().parent.parent / "data.csv"
HOSTILE_STRINGS = [
    "Sharp'; DROP TABLE upgrades;--",
    "' OR '1'='1",
    '"; DELETE FROM towers; --',
    "Sharp\x00; DROP TABLE upgrades",
    "'; ATTACH DATABASE 'x.db' AS x;--",
]
STRING_FIELDS = ["tower_name", "category", "damage_type"]
TABLES = ["upgrades", "towers", "damage_types"]
ALLOWED_SQL_NAMES = {"SELECT_SQL", "where_sql", "order_sql", "limit_sql"}
ALLOWED_SQL_FSTRING_NAMES = {"column", "tiebreak", "sort_by", "direction"}
SQL_MARKERS = (" = ?", " >= ?", "ORDER BY")


@pytest.fixture
def conn(golden_csv_path: Path):
    connection = build_database(golden_csv_path)
    yield connection
    connection.close()


def upgrade_count(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM upgrades").fetchone()[0]


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


@pytest.mark.parametrize("hostile", HOSTILE_STRINGS)
def test_hostile_damage_type_rejected(conn, hostile):
    with pytest.raises(QueryError):
        search_upgrades(conn, UpgradeFilters(damage_type=hostile))
    assert upgrade_count(conn) == 4
    assert set(TABLES) <= table_names(conn)


@pytest.mark.parametrize("field", ["tower_name", "category"])
@pytest.mark.parametrize("hostile", HOSTILE_STRINGS)
def test_hostile_exact_filters_return_empty(conn, field, hostile):
    assert search_upgrades(conn, UpgradeFilters(**{field: hostile})) == []
    assert upgrade_count(conn) == 4
    assert set(TABLES) <= table_names(conn)


@pytest.mark.parametrize("hostile", HOSTILE_STRINGS)
def test_hostile_sort_by_rejected(conn, hostile):
    with pytest.raises(ValueError, match="Cannot sort by"):
        search_upgrades(conn, sort_by=hostile)
    assert upgrade_count(conn) == 4
    assert set(TABLES) <= table_names(conn)


@pytest.mark.parametrize("field", STRING_FIELDS)
@given(text=st.text())
@settings(max_examples=75, deadline=None)
def test_arbitrary_text_filters_only_raise_value_error(field, text):
    connection = build_database(GOLDEN_CSV)
    try:
        try:
            search_upgrades(connection, UpgradeFilters(**{field: text}))
        except ValueError:
            pass
        assert upgrade_count(connection) == 4
        assert set(TABLES) <= table_names(connection)
    finally:
        connection.close()


@given(text=st.text())
@settings(max_examples=75, deadline=None)
def test_arbitrary_sort_by_only_raises_value_error(text):
    connection = build_database(GOLDEN_CSV)
    try:
        try:
            search_upgrades(connection, sort_by=text)
        except ValueError:
            pass
        assert upgrade_count(connection) == 4
    finally:
        connection.close()


def test_single_statement_per_execute(conn):
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    filters = UpgradeFilters(tower_name=HOSTILE_STRINGS[0], category=HOSTILE_STRINGS[1])
    search_upgrades(conn, filters, sort_by="range", limit=3)
    with pytest.raises(QueryError):
        search_upgrades(conn, UpgradeFilters(damage_type=HOSTILE_STRINGS[0]))
    conn.set_trace_callback(None)
    assert statements
    for statement in statements:
        without_literals = re.sub(r"'(?:[^']|'')*'", "''", statement)
        assert not re.search(r";\s*\S", without_literals), statement


def query_tree(repo_root: Path) -> ast.Module:
    return ast.parse((repo_root / "btd6" / "query.py").read_text())


def is_execute_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
    )


def is_safe_sql_argument(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.Name):
        return node.id in ALLOWED_SQL_NAMES
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return is_safe_sql_argument(node.left) and is_safe_sql_argument(node.right)
    return False


def test_execute_calls_only_use_constants_and_known_fragments(repo_root):
    calls = [node for node in ast.walk(query_tree(repo_root)) if is_execute_call(node)]
    assert len(calls) >= 2
    for call in calls:
        assert is_safe_sql_argument(call.args[0]), ast.unparse(call)


def test_sql_fstrings_interpolate_only_trusted_names(repo_root):
    checked = 0
    for node in ast.walk(query_tree(repo_root)):
        if not isinstance(node, ast.JoinedStr):
            continue
        literal = "".join(part.value for part in node.values if isinstance(part, ast.Constant))
        if not any(marker in literal for marker in SQL_MARKERS):
            continue
        checked += 1
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        assert names <= ALLOWED_SQL_FSTRING_NAMES, ast.unparse(node)
    assert checked >= 3


def test_no_format_or_percent_sql_building(repo_root):
    source = (repo_root / "btd6" / "query.py").read_text()
    assert ".format(" not in source
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            assert not isinstance(node.left, ast.Constant), ast.unparse(node)
