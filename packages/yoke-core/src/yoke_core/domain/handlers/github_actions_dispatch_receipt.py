"""Read the immutable inputs and run identity of a scoped workflow dispatch.

A caller reusing a content identity must recover the first dispatch's actual
commit input rather than send a different payload with the same request id.
The existing durable intent owns these facts; telemetry is never consulted.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from yoke_contracts.api.function_call import (
    FunctionCallRequest,
    FunctionError,
    HandlerOutcome,
)
from yoke_contracts.github_app_installation_permissions import (
    GITHUB_ACTIONS_READ_PERMISSION_LEVELS,
)
from yoke_core.domain.github_workflow_dispatch_intents import (
    DispatchIntentStoreError,
    latest_intent,
)
from yoke_core.domain.handlers.github_actions_set import _validate_and_resolve_auth

FUNCTION_ID = "github_actions.dispatch_receipt.get"


class DispatchReceiptRequest(BaseModel):
    project: str = Field(..., min_length=1)
    dispatch_request_id: str = Field(..., min_length=1)


class DispatchReceiptResponse(BaseModel):
    found: bool
    inputs: dict[str, str] = Field(default_factory=dict)
    run_id: str = ""
    state: str = ""


def handle_dispatch_receipt_get(request: FunctionCallRequest) -> HandlerOutcome:
    payload, _resolved, error = _validate_and_resolve_auth(
        request,
        DispatchReceiptRequest,
        FUNCTION_ID,
        required_permissions=GITHUB_ACTIONS_READ_PERMISSION_LEVELS,
    )
    if error is not None:
        return error
    try:
        intent = latest_intent(payload.dispatch_request_id)
    except DispatchIntentStoreError as exc:
        return HandlerOutcome(
            result_payload={},
            primary_success=False,
            error=FunctionError(
                code="workflow_dispatch_state_unavailable",
                message=str(exc),
                recovery_hint="Restore the control-plane intent read, then retry the same request id.",
            ),
        )
    # Match the dispatch writer's project scope. Hide foreign records rather
    # than expose their inputs to a caller authorized for another project.
    scope = request.options.get("authorized_project_id")
    if scope is None or (
        intent and intent.authorization_scope != f"project:{int(scope)}"
    ):
        return HandlerOutcome(
            result_payload={},
            primary_success=False,
            error=FunctionError(
                code="workflow_dispatch_scope_mismatch",
                message="The dispatch receipt is outside this authorized project scope.",
                recovery_hint="Read with the project that owns the dispatch request.",
            ),
        )
    result = DispatchReceiptResponse(found=intent is not None)
    if intent:
        result.inputs = dict(intent.inputs)
        result.run_id = intent.workflow_run_id
        result.state = intent.state
    return HandlerOutcome(result_payload=result.model_dump(), primary_success=True)


REGISTRATIONS = [
    {
        "function_id": FUNCTION_ID,
        "handler": handle_dispatch_receipt_get,
        "request_model": DispatchReceiptRequest,
        "response_model": DispatchReceiptResponse,
        "stability": "stable",
        "owner_module": __name__,
        "target_kinds": ["global"],
        "side_effects": [],
        "emitted_event_names": [],
        "guardrails": ["project_auth_required", "dispatch_project_scope"],
        "adapter_status": "live",
        "claim_required_kind": None,
        "ambient_session_required": False,
        "minimum_serving_version": "next-release",
    }
]
