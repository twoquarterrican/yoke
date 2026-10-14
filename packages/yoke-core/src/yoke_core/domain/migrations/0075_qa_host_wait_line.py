"""Move queued Test Machine waits into their own ``qa_host_waits`` line.

Before this entry a host waiter was only a QA plan execution whose
``release_reason`` carried a ``{"kind": "qa_host_wait", ...}`` JSON
document, and a reserved turn was a ``QA_HOST`` claim whose reason named
that execution. Builds carrying this entry read the line from
``qa_host_waits`` alone, so every live queued execution becomes one row
there — ``reserved`` when its turn is already held for it, otherwise
``waiting`` — and its ``release_reason`` becomes plain prose.

The table DDL is written here rather than imported from
``qa_host_wait_schema``, because a history entry has to load from whatever
build applies it, including a restored archive replaying its history.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from yoke_contracts.timestamps import parse_instant
from yoke_core.domain.db_helpers import instant_parameter
from yoke_core.domain.migration_serving_version import NEXT_RELEASE
from yoke_core.domain.schema_common import _table_exists
from yoke_core.domain.schema_init_apply import execute_schema_script

#: Older builds rebuild the line from ``release_reason`` and would lose it.
MINIMUM_SERVING_VERSION = NEXT_RELEASE
TABLE = "qa_host_waits"
WAIT_KIND = "qa_host_wait"
TURN_REASON = "qa-host-turn:"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS qa_host_waits (
    id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    actor_id INTEGER NOT NULL,
    queued_at TIMESTAMPTZ NOT NULL,
    qa_plan_execution_id TEXT REFERENCES qa_plan_executions(id),
    state TEXT NOT NULL CHECK(state IN ('waiting','reserved','granted','cancelled')),
    claim_id INTEGER REFERENCES work_claims(id),
    resume_command TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    settled_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_qa_host_waits_live_session
    ON qa_host_waits(machine_id, session_id)
    WHERE state IN ('waiting','reserved');
CREATE INDEX IF NOT EXISTS idx_qa_host_waits_line
    ON qa_host_waits(machine_id, state, queued_at);
"""


def _wait(value: object) -> dict[str, Any] | None:
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError):
        return None
    if isinstance(parsed, dict) and parsed.get("kind") == WAIT_KIND:
        return parsed
    return None


def _reserved_claim(conn: Any, execution_id: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM work_claims WHERE reason=%s AND released_at IS NULL "
        "ORDER BY id LIMIT 1",
        (TURN_REASON + execution_id,),
    ).fetchone()
    return None if row is None else int(row[0])


def apply(conn: Any) -> None:
    if not (
        _table_exists(conn, "qa_plan_executions") and _table_exists(conn, "work_claims")
    ):
        return
    execute_schema_script(conn, CREATE_SQL)
    rows = conn.execute(
        "SELECT id,session_id,actor_id,state,release_reason FROM qa_plan_executions "
        "WHERE release_reason LIKE %s ORDER BY id",
        ("%" + WAIT_KIND + "%",),
    ).fetchall()
    for execution_id, session_id, actor_id, state, release_reason in rows:
        wait = _wait(release_reason)
        if wait is None:
            continue
        machine = str(wait["machine"])
        live = state in {"waiting", "active"}
        queued = conn.execute(
            "SELECT 1 FROM qa_host_waits WHERE machine_id=%s AND session_id=%s "
            "AND state IN ('waiting','reserved')",
            (machine, session_id),
        ).fetchone()
        if live and queued is None and actor_id is not None:
            claim_id = _reserved_claim(conn, str(execution_id))
            conn.execute(
                "INSERT INTO qa_host_waits(id,machine_id,session_id,actor_id,"
                "queued_at,qa_plan_execution_id,state,claim_id,resume_command,"
                "rationale) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    str(uuid4()),
                    machine,
                    session_id,
                    int(actor_id),
                    instant_parameter(conn, parse_instant(wait["queued_at"])),
                    execution_id,
                    "waiting" if claim_id is None else "reserved",
                    claim_id,
                    str(wait.get("resume_command") or ""),
                    str(wait.get("rationale") or ""),
                ),
            )
        conn.execute(
            "UPDATE qa_plan_executions SET release_reason=%s WHERE id=%s",
            (
                f"waiting for QA host {machine}" if state == "waiting" else None,
                execution_id,
            ),
        )


def invariants(conn: Any) -> None:
    if not (
        _table_exists(conn, "qa_plan_executions") and _table_exists(conn, "work_claims")
    ):
        return
    assert _table_exists(conn, TABLE), (
        "qa_host_waits_missing: the Test Machine waiting line has no table; "
        "rerun this entry's rehearsal"
    )


__all__ = ["MINIMUM_SERVING_VERSION", "TABLE", "apply", "invariants"]
