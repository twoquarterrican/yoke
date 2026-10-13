"""Named-project misses on a control plane, with an operator-readable cause."""

from __future__ import annotations

import os
from typing import Any, Collection

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
from yoke_core.domain.function_project_selection import project_selection_missing


def unresolved_project_response(
    conn: Any,
    request: FunctionCallRequest,
    entry: RegistryEntry,
    visible_project_ids: Collection[int] | None,
) -> FunctionCallResponse:
    if project_selection_missing(request):
        from yoke_core.domain.project_selection import missing_project_on_connection

        return permission_error_response(
            request,
            entry,
            "project_required",
            missing_project_on_connection(
                conn, visible_project_ids=visible_project_ids
            ),
        )
    return permission_error_response(
        request,
        entry,
        "permission_denied",
        "could not resolve a target project for project-scoped function; "
        "name a registered project with --project P or repair the supplied target",
    )


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
    "unresolved_project_response",
    "ProjectNotRegisteredError",
    "control_plevel_label",
    "permission_error_response",
]
