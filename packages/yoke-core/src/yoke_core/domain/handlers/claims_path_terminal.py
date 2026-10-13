"""Transactional terminal mutations for an item holder's path claims."""

from __future__ import annotations

from pydantic import BaseModel

from yoke_contracts.api.function_call import FunctionError, HandlerOutcome
from yoke_contracts.timestamps import format_instant
from yoke_core.domain.handlers.claims_path_models import ReleaseRequest


class CancelResponse(BaseModel):
    claim_id: int
    state: str
    cancelled_at: str | None = None


def _terminal(request, action: str) -> HandlerOutcome:
    from yoke_core.domain import db_helpers, path_claims, path_claims_events
    from yoke_core.domain.path_claims_dependency_propagation import (
        propagate_release_unblock,
    )
    from yoke_core.domain.workflow_item_binding_lock import (
        lock_path_claim_workflow_binding,
    )

    try:
        body = ReleaseRequest.model_validate(request.payload)
        if not body.reason.strip():
            raise ValueError("reason must name why coverage is ending")
    except ValueError as exc:
        return HandlerOutcome(
            primary_success=False,
            error=FunctionError(
                code="payload_invalid", message=f"{action} payload invalid: {exc}"
            ),
        )
    with db_helpers.connect() as conn:
        try:
            lock_path_claim_workflow_binding(conn, body.claim_id)
            claim = path_claims.get_claim(conn, body.claim_id)
            if (
                claim["owner_kind"] != "item"
                or claim["owner_item_id"] != request.target.item_id
            ):
                conn.rollback()
                return HandlerOutcome(
                    primary_success=False,
                    error=FunctionError(
                        code="claim_owner_mismatch",
                        message=f"path claim {body.claim_id} belongs to another owner; use its owning item and acquire that item's work claim",
                    ),
                )
            changed = claim["state"] != (
                "released" if action == "release" else "cancelled"
            )
            getattr(path_claims, action)(
                conn, claim_id=body.claim_id, reason=body.reason, commit=False
            )
            claim = path_claims.get_claim(conn, body.claim_id)
            if changed:
                getattr(
                    path_claims_events,
                    f"emit_{'released' if action == 'release' else 'cancelled'}",
                )(conn=conn, claim=claim, reason=body.reason, transactional=True)
                propagate_release_unblock(
                    conn, released_claim_id=body.claim_id, commit=False
                )
            conn.commit()
        except path_claims.PathClaimError as exc:
            conn.rollback()
            return HandlerOutcome(
                primary_success=False,
                error=FunctionError(
                    code=f"{action}_failed",
                    message=f"{exc}; inspect `yoke claims path get {body.claim_id}`; terminal claims require fresh registration",
                ),
            )
    clock = "released_at" if action == "release" else "cancelled_at"
    return HandlerOutcome(
        result_payload={
            "claim_id": body.claim_id,
            "state": claim["state"],
            clock: format_instant(claim[clock]) if claim.get(clock) else None,
        }
    )


def handle_release(request) -> HandlerOutcome:
    return _terminal(request, "release")


def handle_cancel(request) -> HandlerOutcome:
    return _terminal(request, "cancel")
