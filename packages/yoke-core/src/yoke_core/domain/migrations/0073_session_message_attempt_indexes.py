"""Index message and target-session attempt lookups without rewriting rows."""

from yoke_core.domain.db_backend import connection_is_postgres


INDEXES = {
    "idx_session_message_attempts_message": "message_id",
    "idx_session_message_attempts_target_session": "target_session_id",
}


def apply(conn) -> None:
    for name, column in INDEXES.items():
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS {name} ON session_message_attempts({column})"
        )


def invariants(conn) -> None:
    for name, column in INDEXES.items():
        if connection_is_postgres(conn):
            row = conn.execute(
                "SELECT i.indisvalid, i.indisready, t.relname, "
                "pg_get_indexdef(i.indexrelid,1,true), i.indnatts, i.indpred IS NULL "
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
                and row[2] == "session_message_attempts"
                and row[3] == column
                and row[4] == 1
                and row[5]
            )
        else:
            row = conn.execute(f"PRAGMA index_info({name})").fetchall()
            valid = [entry[2] for entry in row] == [column]
        assert valid, (
            f"message_attempt_index_invalid: {name} must index {column}; "
            "restore the declared index definition and rerun migration rehearsal"
        )
