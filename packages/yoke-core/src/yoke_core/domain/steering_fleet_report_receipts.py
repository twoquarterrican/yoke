"""Read visible outstanding delivery receipts and ended-session message debt."""

from __future__ import annotations

from typing import Any

from yoke_core.domain.db_helpers import instant_parameter
from yoke_core.domain.steering_fleet_report_detectors import marker, parse_stamp
from yoke_core.domain.session_message_ended_recipient import (
    recipient_has_no_delivery_route,
)
from yoke_core.domain.session_message_visibility import visible_clause
from yoke_core.domain.session_tool_call_projections import open_tool_call_select


def report_receipts(
    conn: Any, *, project_id: int, now: Any, session_id: str | None = None
) -> list[dict[str, Any]]:
    """Keep normal deliveries and unresolved mail with no remaining recipient route.

    The report is read-only. Canonical expiry/cancellation and message visibility
    apply even before receipt-state sweeps converge.
    """
    placeholder = marker(conn)
    visibility, visibility_params = "1=1", []
    if session_id is not None:
        caller = conn.execute(
            f"SELECT actor_id FROM harness_sessions WHERE session_id={placeholder}",
            (session_id,),
        ).fetchone()
        if caller is None or caller[0] is None:
            return []
        visibility, visibility_params = visible_clause(
            conn, actor_id=int(caller[0]), caller_session_id=session_id
        )
    open_call = open_tool_call_select(conn, session_alias="s")
    rows = conn.execute(
        f"""SELECT r.message_id AS message_id,
                   r.session_id AS session_id,
                   r.created_at AS created_at,
                   r.state AS receipt_state, r.injection_count AS injection_count,
                   i.id AS item_id, i.project_sequence AS project_sequence,
                   p.public_item_prefix AS item_prefix, p.slug AS item_project,
                   r.wake_escalation AS wake_escalation,
                   r.wake_attempt_count AS wake_attempt_count,
                   r.routing_snapshot AS routing_snapshot,
                   s.executor_surface AS executor_surface,
                   s.last_tool_call_at AS last_tool_call_at,
                   s.last_heartbeat AS last_heartbeat,
                   s.episode_started_at AS episode_started_at,
                   s.turn_posture AS turn_posture,
                   s.turn_posture_at AS turn_posture_at,
                   s.mode AS mode,
                   s.native_process_gone_at AS native_process_gone_at,
                   s.native_process_gone_evidence AS native_process_gone_evidence,
                   s.ended_at AS ended_at,
                   s.terminated_at AS terminated_at
                   {open_call}
              FROM session_message_recipients r
              JOIN session_messages m ON m.message_id = r.message_id
              JOIN harness_sessions s ON s.session_id = r.session_id
              LEFT JOIN items i ON CAST(i.id AS TEXT) =
                   COALESCE(NULLIF(s.current_item_id, ''), NULLIF(s.recent_item_id, ''))
                   AND i.project_id = r.project_id
              LEFT JOIN projects p ON p.id = i.project_id
             WHERE r.project_id = {placeholder}
               AND m.cancelled_at IS NULL AND m.expires_at > {placeholder}
               AND r.acknowledged_at IS NULL
               AND ((r.state = 'pending' AND COALESCE(r.injection_count, 0) = 0)
                    OR (r.state IN ('pending', 'injected')
                        AND (s.ended_at IS NOT NULL OR s.terminated_at IS NOT NULL)))
               AND {visibility}
             ORDER BY r.created_at, r.message_id""",
        (
            int(project_id),
            instant_parameter(conn, parse_stamp(now)),
            *visibility_params,
        ),
    ).fetchall()
    return [
        record
        for raw in rows
        if (record := dict(raw))["receipt_state"] == "pending"
        and not record.get("injection_count")
        or recipient_has_no_delivery_route(record)
    ]
