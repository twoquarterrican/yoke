"""Acquire path coverage after evaluating current overlap and ordering."""

from __future__ import annotations

from typing import Any, Optional

from yoke_core.domain import workflow_item_binding_lock
from yoke_core.domain import path_claims_dependency_resolver_coordination as dep_edges
from yoke_core.domain.db_helpers import instant_parameter


def activate(
    conn: Any,
    *,
    claim_id: int,
    base_commit_sha: str,
    upstream_claim_id: Optional[int] = None,
) -> None:
    """Acquire the door lock on a planned/blocked claim.

    Idempotent re-activation is a no-op. Same-target overlap is
    re-classified at activate time. Blocked claims wait for release unless
    their persisted ordering condition has already been satisfied.
    """
    from yoke_core.domain.path_claims import (
        _fetch_claim,
        _TERMINAL_STATES,
        _blocked_upstream_id,
        _p,
        _now,
        IllegalTransition,
        InvalidWorkflowBinding,
        IncompatibleOverlap,
        UpstreamNotReleased,
        classify_overlap,
        OverlapClassification,
    )
    from yoke_core.domain.path_claims_dependency_resolver_coordination import (
        upstream_ordering_satisfied,
    )

    workflow_item_binding_lock.lock_path_claim_workflow_binding(
        conn,
        int(claim_id),
    )
    row = _fetch_claim(conn, claim_id)
    owner_kind = row["owner_kind"]
    owner_item_id = row["owner_item_id"] if owner_kind == "item" else None
    if owner_item_id is not None:
        from yoke_core.domain.workflow_item_binding_validation import (
            WorkflowItemBindingError,
            item_binding_runtime_state,
        )

        try:
            item_binding_runtime_state(conn, int(owner_item_id))
        except WorkflowItemBindingError as exc:
            raise InvalidWorkflowBinding(str(exc)) from exc
    state = row["state"]
    if state == "active":
        return  # idempotent — door lock already held
    if state in _TERMINAL_STATES:
        raise IllegalTransition(
            f"cannot activate claim {claim_id} from terminal state {state!r}"
        )
    if state not in ("planned", "blocked"):
        raise IllegalTransition(f"cannot activate claim {claim_id} from {state!r}")

    targets = [
        int(t[0])
        for t in conn.execute(
            f"SELECT target_id FROM path_claim_targets WHERE claim_id = {_p(conn)}",
            (claim_id,),
        )
    ]
    classification = classify_overlap(
        conn,
        target_ids=targets,
        integration_target=row["integration_target"],
        upstream_claim_id=upstream_claim_id,
        exclude_claim_id=claim_id,
        phase="activate",
    )
    if classification is OverlapClassification.INCOMPATIBLE:
        raise IncompatibleOverlap(
            f"claim {claim_id}: another active claim now owns overlapping "
            f"coverage on {row['integration_target']!r}"
        )
    if (
        state == "planned"
        and classification is OverlapClassification.SERIAL_VIA_DEPENDENCY
        and dep_edges.has_active_serial_claim_dependency(
            conn, owner_item_id, row["integration_target"], targets
        )
    ):
        raise UpstreamNotReleased(
            f"claim {claim_id} has an active serial dependency; wait for release"
        )
    ordering_complete = upstream_ordering_satisfied(
        conn,
        dependent_item_id=owner_item_id,
        upstream_claim_id=upstream_claim_id or _blocked_upstream_id(row),
    )
    if state == "blocked" and not ordering_complete:
        if upstream_claim_id is None:
            raise UpstreamNotReleased(
                f"claim {claim_id} is blocked; pass upstream_claim_id to activate"
            )
        expected_upstream = _blocked_upstream_id(row)
        if (
            expected_upstream is not None
            and int(upstream_claim_id) != expected_upstream
        ):
            raise UpstreamNotReleased(
                f"claim {claim_id} is blocked by upstream claim "
                f"{expected_upstream}, not {upstream_claim_id}"
            )
        upstream_state = conn.execute(
            f"SELECT state FROM path_claims WHERE id = {_p(conn)}",
            (upstream_claim_id,),
        ).fetchone()
        if upstream_state is None or upstream_state[0] != "released":
            raise UpstreamNotReleased(
                f"upstream claim {upstream_claim_id} is not released; "
                f"current state {upstream_state[0] if upstream_state else 'missing'!r}"
            )

    conn.execute(
        f"UPDATE path_claims SET state='active', activated_at={_p(conn)}, "
        f"base_commit_sha={_p(conn)}, blocked_reason=NULL WHERE id = {_p(conn)}",
        (instant_parameter(conn, _now()), base_commit_sha, claim_id),
    )
    conn.commit()
