"""Closed PostgreSQL statement grammar for reviewed row repairs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pglast import ast, parse_sql
from pglast.stream import RawStream


class RepairRefusal(ValueError):
    def __init__(self, code: str, reason: str):
        self.code = code
        super().__init__(reason)


SAFE_TYPES = frozenset(
    {
        "text",
        "varchar",
        "bool",
        "int2",
        "int4",
        "int8",
        "numeric",
        "float4",
        "float8",
        "json",
        "jsonb",
        "uuid",
        "date",
        "timestamp",
        "timestamptz",
    }
)
SAFE_FUNCTIONS = frozenset(
    {
        "jsonb_set",
        "jsonb_typeof",
        "jsonb_strip_nulls",
        "jsonb_build_object",
        "jsonb_build_array",
        "to_jsonb",
        "replace",
        "lower",
        "upper",
        "trim",
        "length",
    }
)
SAFE_NODES = frozenset(
    {
        "A_Const",
        "Integer",
        "Float",
        "Boolean",
        "String",
        "ColumnRef",
        "A_Expr",
        "BoolExpr",
        "NullTest",
        "BooleanTest",
        "TypeCast",
        "TypeName",
        "FuncCall",
        "CoalesceExpr",
        "CaseExpr",
        "CaseWhen",
        "A_ArrayExpr",
    }
)
SAFE_OPERATORS = frozenset(
    {
        "=",
        "<>",
        "!=",
        "<",
        ">",
        "<=",
        ">=",
        "+",
        "-",
        "*",
        "/",
        "||",
        "->",
        "->>",
        "#>",
        "#>>",
        "@>",
        "<@",
        "?",
        "?|",
        "?&",
        "#-",
    }
)


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
        raise RepairRefusal(
            "repair_identifier_invalid",
            "Use unquoted lowercase public-table and column names.",
        )
    return '"' + value + '"'


def _walk(node):
    if isinstance(node, ast.Node):
        yield node
        for field in node:
            yield from _walk(getattr(node, field))
    elif isinstance(node, (tuple, list)):
        for child in node:
            yield from _walk(child)


def _names(nodes) -> list[str]:
    return [node.sval for node in nodes or ()]


def _expression(expression) -> set[str]:
    columns = set()
    for node in _walk(expression):
        if isinstance(node, ast.ColumnRef):
            if len(node.fields) != 1 or not isinstance(node.fields[0], ast.String):
                raise RepairRefusal(
                    "repair_column_reference_refused",
                    "Use bare column names from the single repair table.",
                )
            columns.add(node.fields[0].sval)
        if type(node).__name__ not in SAFE_NODES:
            raise RepairRefusal(
                "repair_expression_refused",
                "Use documented built-in repair expressions; subqueries and procedural calls require governed migration review.",
            )
        if isinstance(node, ast.FuncCall):
            names = _names(node.funcname)
            if (
                names[-1] not in SAFE_FUNCTIONS
                or len(names) > 2
                or (len(names) == 2 and names[0] != "pg_catalog")
            ):
                raise RepairRefusal(
                    "repair_function_refused",
                    "Use the documented pure built-in repair functions.",
                )
        if isinstance(node, ast.TypeName):
            names = _names(node.names)
            if (
                names[-1] not in SAFE_TYPES
                or len(names) > 2
                or (len(names) == 2 and names[0] != "pg_catalog")
            ):
                raise RepairRefusal(
                    "repair_type_refused",
                    "Use built-in scalar or JSON types, without custom casts.",
                )
        if isinstance(node, ast.A_Expr):
            names = _names(node.name)
            if names and (
                names[-1] not in SAFE_OPERATORS
                or len(names) > 2
                or (len(names) == 2 and names[0] != "pg_catalog")
            ):
                raise RepairRefusal(
                    "repair_operator_refused",
                    "Use built-in comparison, arithmetic, or JSON operators.",
                )
    return columns


@dataclass(frozen=True)
class RepairStatement:
    table: str
    predicate: str
    mutation: str
    changed_columns: tuple[str, ...]
    read_columns: tuple[str, ...]
    delete: bool


def validate_sql(sql: str, table: str, keys: list[str]) -> RepairStatement:
    identifier(table)
    for key in keys:
        identifier(key)
    try:
        statements = parse_sql(sql)
    except Exception:
        raise RepairRefusal(
            "repair_sql_invalid",
            "SQL could not be parsed; correct its PostgreSQL syntax.",
        ) from None
    if len(statements) != 1 or not isinstance(
        statements[0].stmt, (ast.UpdateStmt, ast.DeleteStmt)
    ):
        raise RepairRefusal(
            "repair_statement_refused",
            "Supply exactly one transactional UPDATE or DELETE; transaction control, DDL, INSERT, and scripts are refused.",
        )
    stmt = statements[0].stmt
    relation = stmt.relation
    if (
        relation.relname != table
        or relation.schemaname not in (None, "public")
        or relation.catalogname
        or relation.alias
    ):
        raise RepairRefusal(
            "repair_target_mismatch",
            "SQL must target the document's single public table without aliases.",
        )
    if (
        stmt.whereClause is None
        or stmt.withClause
        or stmt.returningList
        or getattr(stmt, "fromClause", None)
        or getattr(stmt, "usingClause", None)
    ):
        raise RepairRefusal(
            "repair_unguarded_sql",
            "Supply a WHERE clause and omit CTEs, joins, and RETURNING; the command owns returned row identity.",
        )
    read_columns = _expression(stmt.whereClause)
    changed = []
    for target in getattr(stmt, "targetList", ()) or ():
        identifier(target.name)
        if target.name in keys or target.indirection:
            raise RepairRefusal(
                "repair_key_mutation",
                "Primary keys and assignment indirection cannot be repaired.",
            )
        changed.append(target.name)
        read_columns.update(_expression(target.val))
    relation.schemaname = "public"
    relation.inh = False
    stmt.returningList = tuple(
        ast.ResTarget(val=ast.ColumnRef(fields=(ast.String(sval=key),))) for key in keys
    )
    return RepairStatement(
        table,
        RawStream()(stmt.whereClause),
        RawStream()(stmt),
        tuple(changed),
        tuple(sorted(read_columns)),
        isinstance(stmt, ast.DeleteStmt),
    )
