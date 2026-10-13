"""Status-write backstop for path-claim release.

Recorded landing owns normal release with reason ``landed`` through
:mod:`path_claims_landing`. Exceptional completion paths still release any
remaining claims on the status writer's transaction. Delivery redirects and
pinned terminal stages use their status-specific reasons; this backstop
does not replace recording a landing or authorize editing released coverage.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, List, Optional

from yoke_core.domain import db_backend


_MERGE_BOUNDARY_STATES = ("release",)


def _p(conn: Any) -> str:
    return "%s" if db_backend.connection_is_postgres(conn) else "?"


def _non_terminal_claim_ids_for_item(conn: Any, item_id: int) -> List[int]:
    try:
        p = _p(conn)
        rows = conn.execute(
            "SELECT id FROM path_claims "
            f"WHERE owner_kind = 'item' AND owner_item_id = {p} "
            "AND state IN "
            "('planned', 'blocked', 'active')",
            (item_id,),
        ).fetchall()
    except db_backend.operational_error_types(conn):
        return []
    return [int(r[0]) for r in rows]


def release_claims_on_item_terminal(
    conn: Any,
    *,
    item_id: int,
    new_status: str,
    terminal_statuses: Iterable[str] = (),
    propagate: bool = True,
    released_claim_ids: Optional[List[int]] = None,
    commit: bool = True,
) -> Optional[int]:
    """Release every non-terminal path claim attached to ``item_id``.

    Returns the count of claims that transitioned to ``released``
    (zero is a valid result), or ``None`` when ``new_status`` is
    not one of the terminal-release triggers (``release`` /
    ``done``).
    """
    allowed_terminal_statuses = set(terminal_statuses)
    if not allowed_terminal_statuses:
        try:
            from yoke_core.domain.workflow_runtime import (
                load_item_workflow_runtime,
            )

            allowed_terminal_statuses.update(
                load_item_workflow_runtime(
                    conn,
                    int(item_id),
                ).terminal_stage_ids
            )
        except Exception:
            pass
    if (
        new_status not in _MERGE_BOUNDARY_STATES
        and new_status not in allowed_terminal_statuses
    ):
        return None

    claim_ids = _non_terminal_claim_ids_for_item(conn, item_id)
    if not claim_ids:
        return 0

    try:
        from yoke_core.domain import path_claims_events as _events
    except ImportError:  # pragma: no cover - defensive
        _events = None  # type: ignore[assignment]
    try:
        from yoke_core.domain.path_claims import (
            IllegalTransition,
            get_claim,
            release as _release_claim,
        )
    except ImportError:  # pragma: no cover - defensive
        return 0

    try:
        from yoke_core.domain.path_claims_dependency_propagation import (
            propagate_release_unblock,
        )
    except ImportError:  # pragma: no cover - defensive
        propagate_release_unblock = None  # type: ignore[assignment]

    reason = f"item-{new_status}"
    released = 0
    for claim_id in claim_ids:
        try:
            _release_claim(
                conn,
                claim_id=claim_id,
                reason=reason,
                commit=commit,
            )
        except IllegalTransition:
            if not commit:
                raise
            continue
        released += 1
        if released_claim_ids is not None:
            released_claim_ids.append(claim_id)
        if _events is not None:
            try:
                _events.emit_released(
                    conn=conn,
                    claim=get_claim(conn, claim_id),
                    reason=reason,
                    transactional=not commit,
                )
            except Exception:
                pass
        if propagate and propagate_release_unblock is not None:
            try:
                propagate_release_unblock(
                    conn,
                    released_claim_id=claim_id,
                    commit=commit,
                )
            except Exception:
                pass
    return released


__all__ = [
    "release_claims_on_item_terminal",
]
