"""Function handlers for project onboarding checklist runs."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel

from yoke_contracts.api.function_call import (
    FunctionCallRequest,
    FunctionError,
    HandlerOutcome,
)
from yoke_contracts.onboard_checklist import (
    BRANCH_LOCAL_CHECKOUT,
    OPERATION_INIT,
    SCHEMA_VERSION,
)
from yoke_core.domain import project_onboarding_runs
from yoke_core.domain.project_onboarding_scope import resolve_run


class OnboardChecklistInitRequest(BaseModel):
    run_id: Optional[str] = None
    project_id: Optional[int] = None
    project: Optional[str] = None
    branch: str = BRANCH_LOCAL_CHECKOUT
    checkout_path: Optional[str] = None
    machine_config_path: Optional[str] = None
    github_repo: Optional[str] = None
    row_status: Optional[Dict[str, str]] = None
    evidence: Optional[Dict[str, Any]] = None
    blocker: Optional[Dict[str, Optional[str]]] = None
    note: Optional[Dict[str, Optional[str]]] = None
    metadata: Optional[Dict[str, Any]] = None
    machine_id: Optional[str] = None
    observations: Optional[Dict[str, Any]] = None


class OnboardChecklistInitResponse(BaseModel):
    schema_version: int
    operation: str
    run_id: str
    resumed: bool
    status: str
    rows: list
    summary: dict
    run: dict
    machine_id: Optional[str] = None
    setup_readiness: dict
    execution_profile: Optional[Dict[str, Any]] = None
    profile_changed: bool


class OnboardChecklistRunRequest(BaseModel):
    run_id: Optional[str] = None
    project_id: Optional[int] = None
    project: Optional[str] = None
    branch: Optional[str] = None
    checkout_path: Optional[str] = None
    machine_config_path: Optional[str] = None
    github_repo: Optional[str] = None
    row_status: Optional[Dict[str, str]] = None
    evidence: Optional[Dict[str, Any]] = None
    blocker: Optional[Dict[str, Optional[str]]] = None
    note: Optional[Dict[str, Optional[str]]] = None
    metadata: Optional[Dict[str, Any]] = None
    machine_id: Optional[str] = None
    observations: Optional[Dict[str, Any]] = None


class OnboardChecklistRunResponse(OnboardChecklistInitResponse):
    pass


class OnboardChecklistGetRequest(BaseModel):
    run_id: Optional[str] = None
    project_id: Optional[int] = None
    project: Optional[str] = None
    machine_id: Optional[str] = None
    observations: Optional[Dict[str, Any]] = None


class OnboardChecklistGetResponse(BaseModel):
    schema_version: int
    exists: bool
    run: Optional[Dict[str, Any]] = None


def handle_onboard_checklist_get(request: FunctionCallRequest) -> HandlerOutcome:
    payload = dict(request.payload or {})
    if not payload.get("project_id") and not payload.get("project"):
        if request.target.project_id is not None:
            payload["project"] = str(request.target.project_id)
    project_id, error = _resolve_project_ref(payload, target_project=request.target.project_id)
    if error is not None:
        return error
    conn = project_onboarding_runs.connect()
    try:
        run_id, existing = resolve_run(
            conn,
            run_id=payload.get("run_id"),
            project_id=project_id,
        )
        run = (
            project_onboarding_runs.get_run(
                run_id,
                conn=conn,
                machine_id=payload.get("machine_id"),
                observations=payload.get("observations") or {},
                project_access=True,
            )
            if existing is not None
            else None
        )
        return HandlerOutcome(
            primary_success=True,
            result_payload={
                "schema_version": SCHEMA_VERSION,
                "exists": run is not None,
                "run": run,
            },
        )
    except project_onboarding_runs.ProjectOnboardingRunError as exc:
        return HandlerOutcome(
            primary_success=False,
            error=FunctionError(
                code=str(exc).partition(":")[0],
                message=str(exc),
            ),
        )
    finally:
        conn.close()


def handle_onboard_checklist_init(request: FunctionCallRequest) -> HandlerOutcome:
    return _handle(request, operation=OPERATION_INIT)


def handle_onboard_checklist_run(request: FunctionCallRequest) -> HandlerOutcome:
    return _handle(request, operation=project_onboarding_runs.OPERATION_RUN)


def _handle(request: FunctionCallRequest, *, operation: str) -> HandlerOutcome:
    payload = dict(request.payload or {})
    if not payload.get("project_id") and not payload.get("project"):
        if request.target.project_id is not None:
            payload["project"] = str(request.target.project_id)
    branch = payload.get("branch")
    if branch is None and operation == OPERATION_INIT:
        branch = BRANCH_LOCAL_CHECKOUT
    project_id, project_error = _resolve_project_ref(payload, target_project=request.target.project_id)
    if project_error is not None:
        return project_error
    try:
        result = project_onboarding_runs.update_run(
            run_id=payload.get("run_id"),
            project_id=project_id,
            branch=branch,
            checkout_path=payload.get("checkout_path"),
            machine_config_path=payload.get("machine_config_path"),
            github_repo=payload.get("github_repo"),
            row_status=payload.get("row_status") or {},
            evidence=payload.get("evidence") or {},
            blocker=payload.get("blocker") or {},
            note=payload.get("note") or {},
            metadata=payload.get("metadata") or {},
            machine_id=payload.get("machine_id"),
            observations=payload.get("observations") or {},
            operation=operation,
            project_access=True,
        )
    except project_onboarding_runs.ProjectOnboardingRunError as exc:
        return HandlerOutcome(
            primary_success=False,
            error=FunctionError(
                code=str(exc).partition(":")[0]
                if ":" in str(exc)
                else "onboard_checklist_failed",
                message=str(exc),
            ),
        )
    return HandlerOutcome(result_payload=result, primary_success=True)


def _resolve_project_ref(
    payload: dict[str, Any],
    *, target_project: str | None = None,
) -> tuple[Optional[int], Optional[HandlerOutcome]]:
    """Resolve the run's numeric project id from the payload.

    A numeric ``project_id`` wins; otherwise a ``project`` slug-or-id ref
    (the standalone init shape) resolves through the project registry so
    the run row stays project-attributed. No ref at all stays ``None`` —
    machine-only runs carry no project.
    """
    project_id = payload.get("project_id")
    ref = payload.get("project")
    if project_id is None and not ref:
        return None, None
    from yoke_core.domain.db_helpers import connect
    from yoke_core.domain.project_identity import resolve_project_id

    conn = connect()
    try:
        selected = resolve_project_id(conn, str(project_id if project_id is not None else ref))
        if target_project is not None and resolve_project_id(conn, str(target_project)) != selected:
            return None, HandlerOutcome(primary_success=False, error=FunctionError(
                code="onboarding_project_mismatch",
                message="The payload and authorized project differ; use yoke onboard checklist get --project P for the selected project.",
            ))
        return selected, None
    except LookupError as exc:
        return None, HandlerOutcome(
            primary_success=False,
            error=FunctionError(
                code="project_not_found",
                message=str(exc),
                jsonpath="$.payload.project",
            ),
        )
    finally:
        conn.close()


__all__ = [
    "OnboardChecklistInitRequest",
    "OnboardChecklistInitResponse",
    "OnboardChecklistRunRequest",
    "OnboardChecklistRunResponse",
    "handle_onboard_checklist_init",
    "handle_onboard_checklist_run",
]
