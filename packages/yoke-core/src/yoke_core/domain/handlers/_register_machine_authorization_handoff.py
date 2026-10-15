"""Register the hosted machine-code ingress separately from Inbox actions."""

from yoke_core.domain.handlers import machine_authorization as authorization
from yoke_core.domain.handlers import machine_authorization_handoff as handoff


def register(registry) -> None:
    registry.register(
        "machine_authorization.handoff",
        handoff.handle_handoff,
        handoff.AuthorizationHandoffRequest,
        authorization.AuthorizationResponse,
        stability="stable",
        owner_module=handoff.__name__,
        target_kinds=["global"],
        side_effects=["machine_authorization_insert"],
        emitted_event_names=["YokeFunctionCalled"],
        guardrails=["service_token_required", "org_scope_exact"],
        adapter_status="internal",
        claim_required_kind=None,
        ambient_session_required=False,
        minimum_serving_version="next-release",
    )
