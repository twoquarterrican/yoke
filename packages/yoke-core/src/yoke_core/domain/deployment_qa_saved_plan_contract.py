"""Recover plan selection from durable deployment requirements, never live cases."""

from collections.abc import Mapping
import json

from yoke_core.domain.db_helpers import query_rows
from yoke_core.domain.qa_execution_environment_target import target_digest
from yoke_core.domain.qa_plan_management import QaPlanError
from yoke_core.domain.deployment_qa_presentation_reads import presentation_read


def _refuse(plan_id, detail):
    raise QaPlanError(
        f"qa_saved_plan_contract_invalid: plan {plan_id}: {detail}; preserve the "
        "run's evidence and ask the control-plane operator to reconcile its "
        "saved requirement and target identities before retrying."
    )


def saved_plan_contract(conn, subject, target, plan_id, admitted):
    """An existing group's requirements are its executable contract.

    This is deliberately not a reconstructed reusable plan: its requirements
    already contain expanded baseline variants and effective success policies.
    Materialization may reuse them, but cannot derive new rows from them.
    """
    from yoke_core.domain.deployment_qa_presentation_facts import stage_requirement_rows

    rows = stage_requirement_rows(conn, subject["id"], subject["stage"]["name"])
    if rows is None:
        rows = presentation_read(
            conn,
            (
                "qa_saved_plan_contract",
                subject["id"],
                subject["stage"]["name"],
                plan_id,
            ),
            lambda: query_rows(
                conn,
                "SELECT id,plan_id,plan_case_key,case_position,baseline_position,host_baseline,"
                "method_id,deployment_member_item_id,execution_target_json,execution_target_digest "
                "FROM qa_requirements WHERE deployment_run_id=%s "
                "AND deployment_stage=%s AND plan_id=%s AND method_id IS NOT NULL "
                "AND deployment_member_item_id IS NULL "
                "ORDER BY case_position,baseline_position,id",
                (subject["id"], subject["stage"]["name"], plan_id),
            ),
        )
    groups = {}
    for row in rows:
        # Private copies have no saved plan source. Their authorized conversion
        # remains owned by shared-plan materialization and duplicate retirement.
        if (
            row["deployment_member_item_id"] is not None
            or row["plan_id"] != plan_id
            or not row["method_id"]
        ):
            continue
        try:
            raw = row["execution_target_json"]
            stored = dict(raw) if isinstance(raw, Mapping) else json.loads(str(raw))
            deployment = stored["deployment"]
            shared = deployment.get("shared_plan")
            if shared is not None and not isinstance(shared, Mapping):
                _refuse(plan_id, "shared plan identity is not an object")
            if not shared:
                continue
            if target_digest(stored) != row["execution_target_digest"]:
                _refuse(
                    plan_id, "requirement target digest disagrees with saved target"
                )
            expected = dict(target["deployment"])
            if int(shared["plan_id"]) != plan_id:
                _refuse(plan_id, "shared plan identity disagrees with requirement")
            expected.pop("member_item_id", None)
            expected["shared_plan"] = shared
            if deployment != expected or any(
                stored.get(key) != target.get(key)
                for key in ("tenant", "project", "observation", "environment", "site")
            ):
                _refuse(
                    plan_id, "requirement names another candidate or producer target"
                )
            source = shared.get("source_revision")
            groups.setdefault((row["execution_target_digest"], source), []).append(
                dict(row)
            )
        except (KeyError, TypeError, ValueError) as exc:
            _refuse(plan_id, f"unreadable requirement identity ({exc})")
    if not groups:
        return None
    if len(groups) != 1:
        _refuse(plan_id, "ambiguous saved source or target groups")
    (_, source), requirements = next(iter(groups.items()))
    requirements.sort(
        key=lambda row: (
            row.get("case_position") or 0,
            row.get("baseline_position") or 0,
            row["id"],
        )
    )
    from yoke_core.domain.qa_deployment_case_content_refresh import base_case_key

    identities = {
        (base_case_key(row["plan_case_key"]), row["host_baseline"])
        for row in requirements
    }
    if any(
        (base_case_key(row["plan_case_key"]), row.get("host_baseline"))
        not in identities
        for row in admitted
        if row.get("plan_id") == plan_id
    ):
        _refuse(plan_id, "admitted cases or baseline variants are missing")
    if any(
        not row.get("plan_case_key")
        or row.get("case_position") is None
        or row.get("baseline_position") is None
        for row in requirements
    ):
        _refuse(plan_id, "saved case order is missing")
    return {
        "plan": {
            "id": plan_id,
            "project_id": int(target["project"]["id"]),
            "source_revision": source,
        },
        "cases": [
            {**row, "case_key": row["plan_case_key"], "position": row["case_position"]}
            for row in requirements
        ],
        "materialized_requirements": requirements,
    }
