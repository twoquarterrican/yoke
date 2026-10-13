"""Message idempotency cutover preserves history and uniqueness of live intent."""

import importlib
import sqlite3

import pytest

from runtime.api.domain.test_session_message_support import message_connection

migration = importlib.import_module(
    "yoke_core.domain.migrations.0074_uncancelled_message_idempotency"
)


@pytest.mark.parametrize("sender", [10, None])
def test_cancelled_key_is_reusable_without_changing_the_old_envelope(sender):
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE session_messages(message_id TEXT PRIMARY KEY, sender_actor_id INTEGER, "
        "idempotency_key TEXT, cancelled_at TEXT, body TEXT)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX idx_session_messages_sender_dedupe "
        "ON session_messages(sender_actor_id,idempotency_key) WHERE idempotency_key IS NOT NULL"
    )
    conn.execute(
        "CREATE UNIQUE INDEX idx_session_messages_engine_dedupe "
        "ON session_messages(idempotency_key) WHERE sender_actor_id IS NULL "
        "AND idempotency_key IS NOT NULL"
    )
    conn.execute(
        "INSERT INTO session_messages VALUES('old',?,'intent','cancelled','body')",
        (sender,),
    )
    before = conn.execute("SELECT * FROM session_messages").fetchall()
    migration.apply(conn)
    migration.apply(conn)
    migration.invariants(conn)
    assert conn.execute("SELECT * FROM session_messages").fetchall() == before
    conn.execute(
        "INSERT INTO session_messages VALUES('new',?,'intent',NULL,'body')", (sender,)
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO session_messages VALUES('duplicate',?,'intent',NULL,'body')",
            (sender,),
        )
    assert migration.MINIMUM_SERVING_VERSION == "next-release"


def test_born_universe_has_the_same_uncancelled_intent_indexes():
    migration.invariants(message_connection())
