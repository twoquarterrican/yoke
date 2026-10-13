"""Named-project misses on a control plane, with an operator-readable cause."""

from __future__ import annotations

import os

from yoke_contracts.api.function_call import (
    FunctionCallRequest,
    FunctionCallResponse,
    FunctionError,
)
from yoke_contracts.machine_config.schema import (
    DB_ADMIN_ENV_SUFFIX,
    ENV_OVERRIDE,
)
from yoke_core.domain.yoke_function_registry import RegistryEntry


def project_selection_missing(request: FunctionCallRequest) -> bool:
    """Missing selection differs from an unresolved supplied project or row."""
    target = request.target.model_dump(exclude={"kind"}, exclude_none=True)
    if any(str(value).strip() for value in target.values()):
        return False
    payload = request.payload
    if any(
        str(payload.get(key) or "").strip()
        for key in (
            "project",
            "project_id",
            "slug",
            "scope",
            "entry_id",
            "path_claim_id",
            "env_id",
        )
    ):
        return False
    supplied_target = payload.get("target")
    return not isinstance(supplied_target, dict) or not supplied_target


class ProjectNotRegisteredError(LookupError):
    """A named project ref is not registered on this control plane."""

    def __init__(self, project_ref: str, *, plane: str) -> None:
        self.project_ref = project_ref
        self.plane = plane
        super().__init__(
            f"project {project_ref!r} is not registered on the {plane!r} control plane"
        )


def control_plevel_label() -> str:
    """Name the plane the running process is answering for."""
    env = (
        os.environ.get("YOKE_ENVIRONMENT", "").strip()
        or os.environ.get(ENV_OVERRIDE, "").strip()
        or "this"
    )
    if env.endswith(DB_ADMIN_ENV_SUFFIX):
        env = env[: -len(DB_ADMIN_ENV_SUFFIX)]
    return env or "this"


def permission_error_response(
    request: FunctionCallRequest,
    entry: RegistryEntry,
    code: str,
    message: str,
) -> FunctionCallResponse:
    return FunctionCallResponse(
        success=False,
        function=entry.function_id,
        version=entry.version,
        request_id=request.request_id,
        result={},
        warnings=[],
        error=FunctionError(code=code, message=message),
        event_ids=[],
    )


__all__ = [
    "project_selection_missing",
    "ProjectNotRegisteredError",
    "control_plevel_label",
    "permission_error_response",
]
