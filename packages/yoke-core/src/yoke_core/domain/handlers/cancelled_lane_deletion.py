"""Handler for ``item_worktrees.cancelled_lanes.record``.

A cancelled item's lanes are deleted on each machine after the status
transaction has already released the item claim, so the machine that deleted
them cannot write the Progress Log through the claim-gated append. This
handler is the narrow claim-free write for that one record: it accepts only a
cancelled item and only branches that item's lane rows name, and it appends
what each deleted lane held — its head commits and discarded uncommitted
paths — so the work stays nameable by SHA after its refs are gone.
"""

from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel, Field

from yoke_contracts.api.function_call import (
    FunctionCallRequest,
    FunctionError,
    HandlerOutcome,
)
from yoke_core.domain.progress_log import (
    PROGRESS_LOG_ORDERING,
    PROGRESS_LOG_SECTION,
)

CANCELLED_LANES_HEADLINE = "Cancelled lanes deleted"


class DeletedLane(BaseModel):
    branch: str = Field(..., min_length=1)
    worktree_path: str = ""
    head_sha: str = ""
    remote_head_sha: str = ""
    uncommitted_paths: int = Field(default=0, ge=0)
    kept: List[str] = Field(default_factory=list)


class CancelledLanesRecordRequest(BaseModel):
    lanes: List[DeletedLane] = Field(..., min_length=1)
    machine: str = ""


class CancelledLanesRecordResponse(BaseModel):
    item_id: int
    lanes_recorded: int


def _error(code: str, message: str) -> HandlerOutcome:
    return HandlerOutcome(
        primary_success=False,
        error=FunctionError(code=code, message=message),
    )


def _lane_line(lane: DeletedLane) -> str:
    parts = [f"branch `{lane.branch}`"]
    if lane.worktree_path:
        parts.append(f"worktree `{lane.worktree_path}`")
    parts.append(f"head {lane.head_sha or 'none (no local branch)'}")
    parts.append(f"origin head {lane.remote_head_sha or 'none (no remote branch)'}")
    if lane.uncommitted_paths:
        parts.append(f"{lane.uncommitted_paths} uncommitted path(s) discarded")
    line = "- " + "; ".join(parts)
    for refusal in lane.kept:
        line += f"\n  - not deleted: {refusal}"
    return line


def render_entry(payload: CancelledLanesRecordRequest) -> str:
    where = f" on {payload.machine}" if payload.machine else ""
    lines = [f"Deleted because the item is cancelled{where}:"]
    lines.extend(_lane_line(lane) for lane in payload.lanes)
    return "\n".join(lines)


def _refusal(conn: Any, item_id: int, branches: set[str]) -> str:
    """Name why this item may not record these lanes, or ``""``."""
    from yoke_core.domain import db_backend
    from yoke_core.domain.project_identity import render_item_ref

    marker = "%s" if db_backend.connection_is_postgres(conn) else "?"
    row = conn.execute(
        f"SELECT status FROM items WHERE id = {marker}", (item_id,)
    ).fetchone()
    status = str(row["status"] if hasattr(row, "keys") else row[0]) if row else ""
    ref = render_item_ref(conn, item_id)
    if status != "cancelled":
        return f"{ref} is {status or 'missing'}, not cancelled"
    rows = conn.execute(
        f"SELECT DISTINCT branch FROM item_worktrees WHERE item_id = {marker}",
        (item_id,),
    ).fetchall()
    owned = {str(r["branch"] if hasattr(r, "keys") else r[0]) for r in rows}
    foreign = sorted(branches - owned)
    if foreign:
        return f"{ref} has no lane on branch(es) {', '.join(foreign)}"
    return ""


def handle_record(request: FunctionCallRequest) -> HandlerOutcome:
    """Append the cancelled-lane deletion record to the item's Progress Log."""
    target = request.target
    if target.kind != "item" or target.item_id is None:
        return _error(
            "target_invalid",
            "item_worktrees.cancelled_lanes.record requires target.kind='item' "
            "with public_ref",
        )
    try:
        payload = CancelledLanesRecordRequest.model_validate(request.payload or {})
    except Exception as exc:  # noqa: BLE001 - surface a structured payload error
        return _error("payload_invalid", f"cancelled lanes payload invalid: {exc}")

    from yoke_core.domain import db_helpers, item_field_transform

    item_id = int(target.item_id)
    with db_helpers.connect() as conn:
        refusal = _refusal(conn, item_id, {lane.branch for lane in payload.lanes})
    if refusal:
        return _error("item_not_cancelled_lane", refusal)
    result = item_field_transform.section_append(
        item_id=item_id,
        section=PROGRESS_LOG_SECTION,
        headline=CANCELLED_LANES_HEADLINE,
        content=render_entry(payload),
        ordering=PROGRESS_LOG_ORDERING,
        source="cancelled-lane-deletion",
    )
    if not result.success:
        return _error("write_failed", result.error or "progress_log append failed")
    return HandlerOutcome(
        result_payload=CancelledLanesRecordResponse(
            item_id=item_id, lanes_recorded=len(payload.lanes)
        ).model_dump(),
        primary_success=True,
    )


__all__ = [
    "CANCELLED_LANES_HEADLINE",
    "CancelledLanesRecordRequest",
    "CancelledLanesRecordResponse",
    "handle_record",
    "render_entry",
]
