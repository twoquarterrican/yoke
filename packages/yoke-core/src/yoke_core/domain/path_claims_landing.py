"""Claim ownership ends at landing and starts afresh for rework."""

from __future__ import annotations

from yoke_core.domain import db_backend
from yoke_core.domain.schema_common import _table_exists


def _p(conn):
    return "%s" if db_backend.connection_is_postgres(conn) else "?"


def release_landed_claims(conn, *, item_id: int) -> list[int]:
    """Release and unblock on the landing writer's transaction."""
    from yoke_core.domain import path_claims, path_claims_events
    from yoke_core.domain.path_claims_dependency_propagation import (
        propagate_release_unblock,
    )

    from yoke_core.domain.workflow_item_binding_lock import lock_item_workflow_bindings

    lock_item_workflow_bindings(conn, [item_id])
    ids = [
        int(row[0])
        for row in conn.execute(
            "SELECT id FROM path_claims WHERE owner_kind='item' "
            f"AND owner_item_id={_p(conn)} AND state IN ('planned','blocked','active') ORDER BY id",
            (item_id,),
        ).fetchall()
    ]
    for claim_id in ids:
        path_claims.release(conn, claim_id=claim_id, reason="landed", commit=False)
        path_claims_events.emit_released(
            conn=conn,
            claim=path_claims.get_claim(conn, claim_id),
            reason="landed",
            transactional=True,
        )
    for claim_id in ids:
        propagate_release_unblock(conn, released_claim_id=claim_id, commit=False)
    return ids


def awaits_delivery(conn, item_id: int) -> bool:
    """Recorded landing plus a pinned stage that treats the work as merged."""
    from yoke_core.domain.workflow_runtime import load_item_workflow_runtime

    if not _table_exists(conn, "item_landings"):
        return False
    row = conn.execute(
        f"SELECT status FROM items WHERE id={_p(conn)}", (item_id,)
    ).fetchone()
    if row is None or not load_item_workflow_runtime(conn, item_id).stage_implies_merge(
        str(row[0])
    ):
        return False
    return (
        conn.execute(
            f"SELECT 1 FROM item_landings WHERE item_id={_p(conn)} LIMIT 1",
            (item_id,),
        ).fetchone()
        is not None
    )


def needs_rework_coverage(conn, item_id: int) -> bool:
    """A prior landing released coverage; no open replacement covers rework."""
    if not _table_exists(conn, "path_claims"):
        return False
    p = _p(conn)
    return (
        conn.execute(
            "SELECT 1 FROM path_claims WHERE owner_kind='item' "
            f"AND owner_item_id={p} AND state='released' AND release_reason='landed' "
            "AND NOT EXISTS (SELECT 1 FROM path_claims fresh WHERE fresh.owner_kind='item' "
            f"AND fresh.owner_item_id={p} AND fresh.state IN ('planned','blocked','active')) LIMIT 1",
            (item_id, item_id),
        ).fetchone()
        is not None
    )


def rework_recovery(conn, item_id: int) -> str:
    from yoke_core.domain.project_identity import render_item_ref

    from yoke_core.domain.path_claims_rework_guard import recovery

    return recovery(render_item_ref(conn, item_id))


def evaluate_rework_coverage(*, conn, item_id, target_status, workflow, **_):
    from yoke_core.domain.workflow_delivery_status_gates import activation_stage_index

    activation = activation_stage_index(workflow)
    position = workflow.stage_index(target_status)
    if (
        activation is None
        or position is None
        or position < activation
        or workflow.stage_implies_merge(target_status)
    ):
        return None
    if not needs_rework_coverage(conn, item_id):
        return None
    return {
        "success": False,
        "error_code": "GATE_PATH_CLAIM_REWORK_COVERAGE",
        "error": rework_recovery(conn, item_id),
    }
