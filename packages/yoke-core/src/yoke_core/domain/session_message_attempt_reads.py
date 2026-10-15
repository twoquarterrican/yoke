"""Body-free message-attempt evidence for authorized message reads."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from yoke_contracts.timestamps import format_instant, parse_instant

from yoke_contracts.session_control.evidence import redacted_evidence_document
from yoke_core.domain import db_backend, json_helper


ATTEMPT_READ_LIMIT = 500
_READ_BATCH = ContextVar("message_attempt_read_batch", default=None)
_COLUMNS = (
    "attempt_id,target_session_id,broker_session_id,attempt_kind,"
    "adapter_revision,started_at,completed_at,result_code,evidence"
)


@contextmanager
def message_attempt_read_batch(conn, message_ids):
    """Prefetch every group's bounded product window without decoding shortcuts."""
    placeholders = ",".join(_marker(conn) for _ in message_ids)
    rows = (
        conn.execute(
            "SELECT "
            + _COLUMNS
            + ",message_id,attempt_count FROM (SELECT "
            + _COLUMNS
            + ",message_id,COUNT(*) OVER (PARTITION BY message_id) AS attempt_count,"
            "ROW_NUMBER() OVER (PARTITION BY message_id ORDER BY started_at,attempt_id) AS position "
            f"FROM session_message_attempts WHERE message_id IN ({placeholders})) grouped "
            f"WHERE position <= {ATTEMPT_READ_LIMIT} ORDER BY message_id,position",
            tuple(message_ids),
        ).fetchall()
        if message_ids
        else []
    )
    groups = {str(key): (0, []) for key in message_ids}
    for row in rows:
        key = str(row[9])
        _, attempts = groups[key]
        attempts.append(tuple(row[index] for index in range(9)))
        groups[key] = (int(row[10]), attempts)
    token = _READ_BATCH.set((conn, groups))
    try:
        yield
    finally:
        _READ_BATCH.reset(token)


def _marker(conn: Any) -> str:
    return "%s" if db_backend.connection_is_postgres(conn) else "?"


def _evidence(value: Any) -> dict[str, str | int]:
    try:
        decoded = json_helper.loads_text(str(value))
    except (TypeError, ValueError):
        decoded = None
    return redacted_evidence_document(decoded)


def _read_rows(conn, message_id):
    marker = _marker(conn)
    total_row = conn.execute(
        f"SELECT COUNT(*) FROM session_message_attempts WHERE message_id={marker}",
        (message_id,),
    ).fetchone()
    rows = conn.execute(
        "SELECT " + _COLUMNS + " "
        f"FROM session_message_attempts WHERE message_id={marker} "
        "ORDER BY started_at,attempt_id LIMIT " + str(ATTEMPT_READ_LIMIT),
        (message_id,),
    ).fetchall()
    return int(total_row[0]) if total_row is not None else 0, rows


def message_attempt_evidence(conn: Any, message_id: str) -> dict[str, Any]:
    """Return bounded attempt facts without leases or native payloads."""
    batch = _READ_BATCH.get()
    total, rows = (
        batch[1][message_id]
        if batch is not None and batch[0] is conn and message_id in batch[1]
        else _read_rows(conn, message_id)
    )
    attempts = [
        {
            "attempt_id": str(row[0]),
            "target_session_id": str(row[1]),
            "broker_session_id": str(row[2]) if row[2] is not None else None,
            "attempt_kind": str(row[3]),
            "adapter_revision": str(row[4]) if row[4] is not None else None,
            "started_at": format_instant(parse_instant(row[5])),
            "completed_at": format_instant(parse_instant(row[6]))
            if row[6] is not None
            else None,
            "result_code": str(row[7]) if row[7] is not None else None,
            "evidence": _evidence(row[8]),
        }
        for row in rows
    ]
    return {
        "attempts": attempts,
        "attempt_count": total,
        "attempts_truncated": total > len(attempts),
    }


__all__ = ["ATTEMPT_READ_LIMIT", "message_attempt_evidence"]
