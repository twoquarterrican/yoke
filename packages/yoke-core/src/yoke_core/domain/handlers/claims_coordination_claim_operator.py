"""Steering-seat recovery for stranded coordination claims."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from yoke_contracts.api.function_call import (
    FunctionCallRequest,
    FunctionError,
    HandlerOutcome,
)


class OperatorIdentityRequired(ValueError):
    """The request carries no authenticated actor to record on the release."""


class OperatorReleaseRequest(BaseModel):
    project_id: str | None = None
    key: str
    claim_id: int
    holder_session_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class OperatorReleaseResponse(BaseModel):
    released: bool
    claim_id: int
    project_id: int | None
    key: str
    prior_session_id: str
    operator_actor_id: int
    operator_reason: str
    released_at: str


def _error(code: str, message: str) -> HandlerOutcome:
    return HandlerOutcome(
        primary_success=False,
        error=FunctionError(code=code, message=message),
    )


def handle_operator_release(request: FunctionCallRequest) -> HandlerOutcome:
    """Release the exact claim a steering-seat holder reviewed.

    The dispatcher's ``steering`` claim gate has already required the
    caller's live seat on the claim's project.
    """
    try:
        body = OperatorReleaseRequest.model_validate(request.payload)
    except Exception as exc:
        return _error("payload_invalid", f"operator release payload invalid: {exc}")

    from yoke_core.domain import db_helpers
    from yoke_core.domain.coordination_claims import (
        CoordinationClaimError,
        CoordinationClaimHookContextError,
        CoordinationClaimNotFoundError,
    )
    from yoke_core.domain.coordination_claims_operator import (
        CoordinationClaimChangedError,
        operator_release,
    )

    try:
        with db_helpers.connect() as conn:
            actor_id = _authenticated_actor(request)
            result: dict[str, Any] = operator_release(
                conn,
                project_id=body.project_id,
                key=body.key,
                operator_reason=body.reason,
                expected_claim_id=body.claim_id,
                expected_holder_session_id=body.holder_session_id,
                operator_actor_id=actor_id,
            )
    except CoordinationClaimChangedError as exc:
        return _error("claim_changed", str(exc))
    except CoordinationClaimHookContextError as exc:
        return _error("hook_context", str(exc))
    except CoordinationClaimNotFoundError as exc:
        return _error("claim_not_found", str(exc))
    except CoordinationClaimError as exc:
        return _error("claim_error", str(exc))
    except OperatorIdentityRequired as exc:
        return _error("operator_identity_required", str(exc))
    except (LookupError, ValueError) as exc:
        return _error("payload_invalid", str(exc))

    return HandlerOutcome(result_payload=result)


def _authenticated_actor(request: FunctionCallRequest) -> int:
    """Resolve the authenticated actor recorded on the release row."""
    raw_actor = str(request.actor.actor_id or "").strip()
    if not raw_actor.isdigit():
        raise OperatorIdentityRequired(
            "This call carries no authenticated actor; run stranded-claim "
            "recovery from a registered session whose actor holds "
            "claims.release on the claim's project"
        )
    return int(raw_actor)


__all__ = [
    "OperatorReleaseRequest",
    "OperatorReleaseResponse",
    "OperatorIdentityRequired",
    "handle_operator_release",
]
