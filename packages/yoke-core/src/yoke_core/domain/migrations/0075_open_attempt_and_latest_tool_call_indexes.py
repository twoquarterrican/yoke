"""Index open message attempts and each session's latest tool call."""

from yoke_core.domain.db_backend import connection_is_postgres


INDEXES = {
    "idx_session_message_attempts_open_lease": (
        "session_message_attempts",
        ("lease_id",),
        "completed_at IS NULL",
    ),
    "idx_session_message_attempts_open_started": (
        "session_message_attempts",
        ("started_at", "attempt_id"),
        "completed_at IS NULL",
    ),
    "idx_session_tool_calls_session_id_id": (
        "session_tool_calls",
        ("session_id", "id"),
        None,
    ),
}


def _create_sql(name: str, table: str, columns: tuple[str, ...], predicate) -> str:
    where = f" WHERE {predicate}" if predicate else ""
    return f"CREATE INDEX IF NOT EXISTS {name} ON {table}({', '.join(columns)}){where}"


def apply(conn) -> None:
    for name, (table, columns, predicate) in INDEXES.items():
        conn.execute(_create_sql(name, table, columns, predicate))


def _normalize(sql: str) -> str:
    return (
        "".join(sql.lower().split())
        .replace("(", "")
        .replace(")", "")
        .replace("ifnotexists", "")
    )


def invariants(conn) -> None:
    for name, (table, columns, predicate) in INDEXES.items():
        if connection_is_postgres(conn):
            row = conn.execute(
                "SELECT i.indisvalid, i.indisready, t.relname, "
                "pg_get_expr(i.indpred,i.indrelid), i.indnatts, "
                "ARRAY(SELECT pg_get_indexdef(i.indexrelid,k,true) "
                "FROM generate_series(1,i.indnatts) AS k ORDER BY k) "
                "FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "JOIN pg_class t ON t.oid=i.indrelid "
                "WHERE c.relname=%s AND n.nspname=current_schema()",
                (name,),
            ).fetchone()
            valid = (
                row
                and row[0]
                and row[1]
                and row[2] == table
                and _normalize(row[3] or "") == _normalize(predicate or "")
                and row[4] == len(columns)
                and tuple(row[5]) == columns
            )
        else:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)
            ).fetchone()
            valid = row and _normalize(row[0]) == _normalize(
                _create_sql(name, table, columns, predicate)
            )
        assert valid, (
            f"open_lookup_index_invalid: {name} must index {table}"
            f"({', '.join(columns)}){' WHERE ' + predicate if predicate else ''}; "
            "restore the declared index definition and rerun migration rehearsal"
        )
