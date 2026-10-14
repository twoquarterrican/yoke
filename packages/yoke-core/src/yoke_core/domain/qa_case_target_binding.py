"""Bind a method case context to its stored or registered execution target."""

import json


def bind_case_target(conn, row, context):
    """Validate the stored target and expose shared-group command selectors."""
    from yoke_core.domain.qa_case_execution_context import QaCaseExecutionError

    plan_id = row["plan_id"]
    raw_target = row["execution_target_json"]
    if raw_target and row["execution_target_digest"]:
        try:
            execution_target = json.loads(str(raw_target))
        except (TypeError, ValueError) as exc:
            raise QaCaseExecutionError(
                "materialized QA case has an invalid execution target"
            ) from exc
        if not isinstance(execution_target, dict):
            raise QaCaseExecutionError(
                "materialized QA case has an invalid execution target"
            )
        from yoke_core.domain.qa_environment_execution_target import (
            require_case_endpoint,
        )
        from yoke_core.domain.qa_execution_environment_target import (
            QaExecutionTargetError,
            require_case_target,
            require_runtime_target,
            target_digest,
        )

        if target_digest(execution_target) != str(row["execution_target_digest"]):
            raise QaCaseExecutionError(
                "materialized QA case execution target digest does not match"
            )
        require_runtime_target(execution_target)
        require_case_target(context, execution_target)
        if plan_id is None and row["deployment_stage"] is None:
            try:
                require_case_endpoint(context, execution_target)
            except QaExecutionTargetError as exc:
                raise QaCaseExecutionError(str(exc)) from exc
        context["execution_target"] = execution_target
        context["execution_target_digest"] = str(row["execution_target_digest"])
        if (execution_target.get("deployment") or {}).get("shared_plan"):
            from yoke_core.domain.deployment_qa_shared_plans import (
                requirement_subject,
                group_members,
            )
            from yoke_core.domain.project_identity import render_item_ref

            group = requirement_subject(
                conn, int(row["requirement_id"]), require_active=False
            )
            context["shared_plan_member_refs"] = [
                render_item_ref(conn, member)
                for member in group_members(conn, group, execution_target)
            ]
    elif plan_id is not None:
        raise QaCaseExecutionError(
            "materialized QA case has no execution target; rematerialize "
            "it after binding the plan target"
        )
    elif row["deployment_stage"] is not None:
        from yoke_core.domain.deployment_qa_direct_case_target import (
            restore_missing_deployment_case_target,
        )

        try:
            restore_missing_deployment_case_target(conn, row, context)
        except (LookupError, TypeError, ValueError) as exc:
            raise QaCaseExecutionError(str(exc)) from exc
    elif str(row["target_env"] or "").strip():
        from yoke_core.domain.qa_environment_execution_target import (
            require_case_endpoint,
            resolve_named_environment_execution_target,
        )
        from yoke_core.domain.qa_execution_environment_target import (
            QaExecutionTargetError,
            require_case_target,
            target_digest,
        )

        try:
            execution_target = resolve_named_environment_execution_target(
                conn,
                project_id=int(row["project_id"]),
                environment_name=str(row["target_env"]).strip(),
            )
            require_case_target(context, execution_target)
            require_case_endpoint(context, execution_target)
        except QaExecutionTargetError as exc:
            raise QaCaseExecutionError(str(exc)) from exc
        context["execution_target"] = execution_target
        context["execution_target_digest"] = target_digest(execution_target)
