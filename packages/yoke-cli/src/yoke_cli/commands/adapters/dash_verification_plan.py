"""Project-scoped verification-plan resolution for Dash filing."""

from __future__ import annotations

from typing import Mapping

from yoke_cli.commands import _helpers
from yoke_cli.transport.dispatcher import build_actor, call_dispatcher
from yoke_contracts.api.function_call import TargetRef


class DashVerificationPlanError(ValueError):
    """A Dash verification-plan reference could not resolve safely."""


def resolve_dash_verification_plan(
    reference: str,
    *,
    project: str | None,
    session_id: str | None,
) -> int:
    """Resolve an integer id directly or a slug within one project."""
    try:
        return int(reference)
    except ValueError:
        pass

    if project is None:
        raise DashVerificationPlanError(
            f"verification plan slug {reference!r} needs project context; "
            "pass --project P or run from a registered checkout"
        )

    _helpers.ensure_handlers_loaded()
    fetched = call_dispatcher(
        function_id="qa.plan.get",
        target=TargetRef(kind="global"),
        payload={"project": project, "plan_id": reference},
        actor=build_actor(session_id=session_id),
    )
    if not fetched.success:
        detail = (
            fetched.error.message if fetched.error is not None else "qa.plan.get failed"
        )
        raise DashVerificationPlanError(
            f"could not resolve verification plan slug {reference!r} "
            f"in project {project!r}: {detail}"
        )

    plan = (fetched.result or {}).get("plan")
    if not isinstance(plan, Mapping):
        raise DashVerificationPlanError(
            f"qa.plan.get returned no plan document for slug {reference!r} "
            f"in project {project!r}"
        )
    if plan.get("retired_at") is not None:
        raise DashVerificationPlanError(
            f"verification plan slug {reference!r} in project {project!r} is "
            "retired; name an active plan from `yoke qa plan list --project P`"
        )
    try:
        return int(plan["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DashVerificationPlanError(
            f"verification plan slug {reference!r} in project {project!r} "
            "has no valid integer id"
        ) from exc


__all__ = [
    "DashVerificationPlanError",
    "resolve_dash_verification_plan",
]
