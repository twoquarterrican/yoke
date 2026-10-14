"""Retire a wake hold only when its recorded native is proven gone."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from yoke_contracts.session_control.wake_delivery import NATIVE_TURN_RUNNING_RESULT
from yoke_core.domain.db_helpers import instant_parameter
from yoke_core.domain.session_message_types import parse_timestamp
from yoke_core.domain.session_relay_storage import marker


def held_native_is_gone(record: Mapping[str, Any], evidence: Mapping[str, Any]) -> bool:
    """Compare a declined wake's custody identity with the latest death proof."""
    from yoke_core.domain.session_native_process_observation import (
        current_native_process_observation,
    )

    observation = current_native_process_observation(record, include_expected_exit=True)
    if observation is None:
        return False
    return _same_native(evidence, observation["evidence"])


def _same_native(held: Mapping[str, Any], dead: Mapping[str, Any]) -> bool:
    pid = held.get("running_native_pid")
    if not isinstance(pid, int) or pid not in (dead.get("pids") or []):
        return False
    start = held.get("running_native_start_time")
    starts = dead.get("process_start_times") or {}
    return bool(start and isinstance(starts, Mapping) and starts.get(str(pid)) == start)


def recover_dead_native_holds(
    conn: Any, session_id: str, evidence: Mapping[str, Any], *, death_at: datetime
) -> None:
    """Reopen pending receipts held by this process without changing attempts.

    No wake ran during those declines. Reset their exhausted hold budget,
    including explicit wakes whose nonzero count would otherwise forbid retry.
    A newer or open attempt owns its receipt and is never touched. Attempt
    history stays intact as evidence; repeat death reports are idempotent.
    """
    p = marker(conn)
    rows = conn.execute(
        "SELECT r.message_id,a.result_code,a.evidence,a.completed_at,a.attempt_id "
        "FROM session_message_recipients r "
        "JOIN session_messages m ON m.message_id=r.message_id "
        "JOIN session_message_attempts a ON a.attempt_id=("
        "SELECT latest.attempt_id FROM session_message_attempts latest "
        "WHERE latest.message_id=r.message_id AND latest.target_session_id=r.session_id "
        "ORDER BY latest.started_at DESC,latest.attempt_id DESC LIMIT 1) "
        f"WHERE r.session_id={p} AND r.state='pending' "
        f"AND m.cancelled_at IS NULL AND m.expires_at>{p}",
        (session_id, instant_parameter(conn, death_at)),
    ).fetchall()
    for row in rows:
        if row[1] != NATIVE_TURN_RUNNING_RESULT or row[3] is None:
            continue
        if parse_timestamp(row[3]) > death_at:
            continue
        try:
            held = json.loads(str(row[2] or "{}"))
        except ValueError:
            continue
        if not isinstance(held, Mapping) or not _same_native(held, evidence):
            continue
        conn.execute(
            "UPDATE session_message_recipients SET wake_attempt_count=0,"
            f"wake_escalation=NULL,wake_after={p} "
            f"WHERE message_id={p} AND session_id={p} AND state='pending' "
            "AND NOT EXISTS (SELECT 1 FROM session_message_attempts a "
            "WHERE a.message_id=session_message_recipients.message_id "
            "AND a.target_session_id=session_message_recipients.session_id "
            "AND a.completed_at IS NULL) "
            "AND (SELECT latest.attempt_id FROM session_message_attempts latest "
            "WHERE latest.message_id=session_message_recipients.message_id "
            "AND latest.target_session_id=session_message_recipients.session_id "
            f"ORDER BY latest.started_at DESC,latest.attempt_id DESC LIMIT 1)={p}",
            (instant_parameter(conn, death_at), row[0], session_id, row[4]),
        )
