"""Run-driver authority for bound-source diagnosis and dispatch preparation."""

from pydantic import BaseModel
from yoke_contracts.api.function_call import HandlerOutcome
from yoke_core.domain.deployment_run_stale_bound_sources import (
    BOUND_SOURCES_CURRENT_FUNCTION_ID as FUNCTION_ID,
)
from yoke_core.domain.handlers.deployment_common import run_id, error
from yoke_core.domain.handlers.deployment_run_execution import require_run_driver


class Request(BaseModel):
    pass


class Response(BaseModel):
    stale: list[dict[str, str]] = []
    unverified: str = ""


def handle(request):
    resolved = run_id(request, FUNCTION_ID)
    if isinstance(resolved, HandlerOutcome):
        return resolved
    if refusal := require_run_driver(request, resolved):
        return refusal
    from yoke_core.domain.db_helpers import connect
    from yoke_core.domain.deployment_run_stale_bound_sources import (
        check_bound_sources_current,
    )

    with connect() as conn:
        stale, unverified = check_bound_sources_current(conn, resolved)
    return HandlerOutcome(
        result_payload={"stale": stale, "unverified": unverified},
        primary_success=True,
    )


class PrepareRequest(BaseModel):
    stage_name: str


class PrepareResponse(BaseModel):
    bound_sources: dict
    rebound: list[dict[str, str]]
    members: list[dict]


def handle_prepare(request):
    from yoke_core.domain.deployment_run_bound_source_prepare import (
        prepare_bound_sources,
    )
    from yoke_core.domain.deployment_run_bound_sources import (
        BOUND_SOURCES_PREPARE_FUNCTION_ID,
    )
    from yoke_core.domain.db_helpers import connect
    from yoke_core.domain.handlers.deployment_run_execution import _member_rows

    resolved = run_id(request, BOUND_SOURCES_PREPARE_FUNCTION_ID)
    if isinstance(resolved, HandlerOutcome):
        return resolved
    if refusal := require_run_driver(request, resolved):
        return refusal
    with connect() as conn:
        try:
            result = prepare_bound_sources(
                conn, resolved, str((request.payload or {}).get("stage_name") or "")
            )
        except (LookupError, ValueError) as exc:
            conn.rollback()
            return error("bound_source_preparation_refused", str(exc))
        result["members"] = _member_rows(resolved, connection=conn)
        conn.commit()
    return HandlerOutcome(result_payload=result, primary_success=True)


def register(registry):
    registry.register(
        FUNCTION_ID,
        handle,
        Request,
        Response,
        stability="stable",
        owner_module=__name__,
        target_kinds=["workflow_run"],
        side_effects=[],
        emitted_event_names=["YokeFunctionCalled"],
        guardrails=["run_driver_required"],
        adapter_status="internal",
        claim_required_kind=None,
        minimum_serving_version="next-release",
    )

    from yoke_core.domain.deployment_run_bound_sources import (
        BOUND_SOURCES_PREPARE_FUNCTION_ID,
    )

    registry.register(
        BOUND_SOURCES_PREPARE_FUNCTION_ID,
        handle_prepare,
        PrepareRequest,
        PrepareResponse,
        stability="stable",
        owner_module=__name__,
        target_kinds=["workflow_run"],
        side_effects=["deployment_runs_update", "deployment_run_items_insert"],
        emitted_event_names=["YokeFunctionCalled"],
        guardrails=["run_driver_required"],
        adapter_status="internal",
        claim_required_kind=None,
        minimum_serving_version="next-release",
    )
