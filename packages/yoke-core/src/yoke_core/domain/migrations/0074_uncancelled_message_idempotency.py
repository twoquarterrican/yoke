"""Cancelled envelopes retain history without reserving message intent keys."""

from yoke_core.domain.db_backend import connection_is_postgres
from yoke_core.domain.migration_serving_version import NEXT_RELEASE


MINIMUM_SERVING_VERSION = NEXT_RELEASE
INDEXES = {
    "idx_session_messages_sender_dedupe": (
        ("sender_actor_id", "idempotency_key"),
        "idempotency_key IS NOT NULL AND cancelled_at IS NULL",
    ),
    "idx_session_messages_engine_dedupe": (
        ("idempotency_key",),
        "sender_actor_id IS NULL AND idempotency_key IS NOT NULL AND cancelled_at IS NULL",
    ),
}


def apply(conn) -> None:
    for name, (columns, predicate) in INDEXES.items():
        conn.execute(f"DROP INDEX IF EXISTS {name}")
        conn.execute(
            f"CREATE UNIQUE INDEX {name} ON session_messages({', '.join(columns)}) "
            f"WHERE {predicate}"
        )


def _normalize(sql: str) -> str:
    return (
        "".join(sql.lower().split())
        .replace("(", "")
        .replace(")", "")
        .replace("ifnotexists", "")
    )


def invariants(conn) -> None:
    for name, (columns, predicate) in INDEXES.items():
        if connection_is_postgres(conn):
            row = conn.execute(
                "SELECT i.indisunique, i.indisvalid, i.indisready, t.relname, "
                "pg_get_expr(i.indpred,i.indrelid), i.indnatts, "
                "pg_get_indexdef(i.indexrelid,1,true), "
                "CASE WHEN i.indnatts>1 THEN pg_get_indexdef(i.indexrelid,2,true) ELSE NULL END "
                "FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "JOIN pg_class t ON t.oid=i.indrelid "
                "WHERE c.relname=%s AND n.nspname=current_schema()",
                (name,),
            ).fetchone()
            valid = (
                row
                and all(row[i] for i in range(3))
                and row[3] == "session_messages"
                and _normalize(row[4] or "") == _normalize(predicate)
                and row[5] == len(columns)
                and tuple(row[6 + i] for i in range(len(columns))) == columns
            )
        else:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)
            ).fetchone()
            valid = row and _normalize(row[0]) == _normalize(
                f"CREATE UNIQUE INDEX {name} ON session_messages({', '.join(columns)}) "
                f"WHERE {predicate}"
            )
        assert valid, (
            f"message_idempotency_index_invalid: {name} must reserve only "
            "uncancelled intents; restore the declared index and rerun rehearsal"
        )
