"""universe.cursor_quota_order.set attributes the calling actor."""

import sqlite3

from yoke_contracts.api.function_call import (
    ActorContext,
    FunctionCallRequest,
    TargetRef,
)
from yoke_core.domain.handlers.quota_pool_order import SET_FUNCTION_ID, handle_set

POOLS = ["Cursor Models", "Other Models"]


def _request(actor_id: str | None) -> FunctionCallRequest:
    return FunctionCallRequest(
        function=SET_FUNCTION_ID,
        actor=ActorContext(actor_id=actor_id, session_id=""),
        target=TargetRef(kind="global"),
        payload={"pools": list(POOLS)},
    )


def test_set_records_the_caller_and_refuses_without_one(monkeypatch) -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE universe_settings ("
        "key TEXT PRIMARY KEY, value TEXT, updated_at TEXT, "
        "updated_by_actor_id INTEGER)"
    )
    monkeypatch.setattr(
        "yoke_core.domain.handlers.quota_pool_order.connect",
        lambda: conn,
    )

    refused = handle_set(_request(None))
    assert refused.primary_success is False
    assert refused.error is not None
    assert refused.error.code == "actor_required"
    assert conn.execute("SELECT COUNT(*) FROM universe_settings").fetchone()[0] == 0

    stored = handle_set(_request("7"))
    assert stored.primary_success, stored.error
    assert stored.result_payload == {"pools": POOLS}
    assert (
        conn.execute(
            "SELECT updated_by_actor_id FROM universe_settings "
            "WHERE key = 'cursor_quota_order'"
        ).fetchone()[0]
        == 7
    )
