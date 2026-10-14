"""Plan subjects shared by members shipping the same source to the same target."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from yoke_core.domain.db_helpers import query_rows
from yoke_core.domain.qa_execution_environment_target import canonical_target


def shared_subject(subject: Mapping, target: Mapping, snapshot: Mapping) -> dict:
    """Keep plan identity, never an attaching member, in the execution target."""
    plan = snapshot["plan"]
    identity = {
        "plan_id": int(plan["id"]),
        "source_revision": plan.get("source_revision"),
    }
    normalized = deepcopy(dict(target))
    normalized["deployment"].pop("member_item_id", None)
    normalized["deployment"]["shared_plan"] = identity
    return {
        **subject,
        "member_item_id": None,
        "member_snapshot": None,
        "shared_plan": identity,
        "shared_snapshot": dict(snapshot),
        "shared_target": normalized,
    }


def shareable_snapshots(
    conn: Any, subject: Mapping, target: Mapping, snapshots: list[dict]
) -> list[dict]:
    """Share member attachments; flow-defined plans keep their declared scope."""
    from yoke_core.domain.qa_deployment_member_attached_plans import (
        attached_member_plan_ids,
        stage_environment_id_for_plan_selection,
    )

    member = subject.get("member_item_id")
    if member is None:
        return []
    ids = set(
        attached_member_plan_ids(
            conn,
            member_item_id=int(member),
            environment_id=stage_environment_id_for_plan_selection(conn, target),
        )
    )
    for value in (subject.get("member_snapshot") or {}).get("plans") or []:
        if (value.get("attachment") or {}).get("qa_phase") == "post_deploy":
            ids.add(int(value["plan"]["id"]))
    return [snapshot for snapshot in snapshots if int(snapshot["plan"]["id"]) in ids]


def member_plan_subjects(conn: Any, subject: Mapping, target: Mapping) -> list[dict]:
    """The plan verdicts this member owes, without other members' plans."""
    if subject.get("member_item_id") is None:
        return []
    from yoke_core.domain.deployment_qa_frozen_plan_selection import member_requirements
    from yoke_core.domain.deployment_qa_plan_selection import selected_plans

    admitted = member_requirements(conn, subject, target=target)
    snapshots = selected_plans(
        conn,
        subject,
        agent_plan=None,
        target=target,
        admitted=admitted,
        allow_empty=True,
    )
    return [
        shared_subject(subject, target, snapshot)
        for snapshot in shareable_snapshots(conn, subject, target, snapshots)
    ]


def resolve_shared_subject(
    conn: Any,
    *,
    run_id: str,
    stage_name: str,
    plan_id: int,
    member_item_id: int | None = None,
    expected_target: Mapping | None = None,
    require_active: bool = True,
) -> dict:
    """Resolve a shared group only through a member that actually selected it."""
    from yoke_core.domain.deployment_qa_stage_contract import (
        deployment_qa_stage_subject,
    )
    from yoke_core.domain.deployment_qa_execution_target import (
        deployment_qa_execution_target,
    )

    members = query_rows(
        conn,
        "SELECT m.item_id FROM deployment_run_items m JOIN items i ON i.id=m.item_id "
        "JOIN qa_plans p ON p.project_id=i.project_id WHERE m.run_id=%s AND p.id=%s ORDER BY m.item_id",
        (run_id, plan_id),
    )
    matches = {}
    for row in members:
        member = int(row["item_id"])
        if member_item_id is not None and member != member_item_id:
            continue
        subject = deployment_qa_stage_subject(
            conn,
            run_id=run_id,
            stage_name=stage_name,
            member_item_id=member,
            require_active=require_active,
        )
        if subject["stage"]["scope"] != "item":
            break
        target = deployment_qa_execution_target(conn, subject)
        for group in member_plan_subjects(conn, subject, target):
            if group["shared_plan"]["plan_id"] != int(plan_id):
                continue
            resolved = deployment_qa_execution_target(conn, group)
            if expected_target is not None and canonical_target(
                resolved
            ) != canonical_target(expected_target):
                continue
            matches[canonical_target(resolved)] = group
    if len(matches) != 1:
        raise ValueError(
            f"shared_plan_subject_unresolved: plan {plan_id} has {len(matches)} matching "
            f"groups in run {run_id} stage {stage_name}; select an attaching --member "
            "to disambiguate, or restore its plan attachment and current producer receipt"
        )
    return next(iter(matches.values()))


def frozen_shared_target(conn: Any, subject: Mapping) -> dict:
    """Freeze endpoints per group while its exact producer receipt is current."""
    import json

    target = dict(subject["shared_target"])
    rows = query_rows(
        conn,
        "SELECT execution_target_json FROM qa_requirements "
        "WHERE deployment_run_id=%s AND deployment_stage=%s "
        "AND deployment_member_item_id IS NULL AND plan_id=%s ORDER BY id",
        (subject["id"], subject["stage"]["name"], subject["shared_plan"]["plan_id"]),
    )
    for row in rows:
        raw = row["execution_target_json"]
        frozen = dict(raw) if isinstance(raw, Mapping) else json.loads(str(raw))
        if all(
            frozen.get(key) == target.get(key)
            for key in ("tenant", "project", "observation", "deployment")
        ):
            return frozen
    return target


def execution_subject(
    conn: Any, execution: Mapping, *, require_active: bool = True
) -> dict:
    """Recover a private or shared subject from its immutable execution target."""
    from yoke_core.domain.deployment_qa_stage_contract import (
        deployment_qa_stage_subject,
    )

    import json

    target = (
        execution.get("execution_target")
        or execution.get("execution_target_json")
        or {}
    )
    if not isinstance(target, Mapping):
        target = json.loads(str(target))
    shared = (target.get("deployment") or {}).get("shared_plan")
    if shared:
        return resolve_shared_subject(
            conn,
            run_id=str(execution["deployment_run_id"]),
            stage_name=str(execution["deployment_stage"]),
            plan_id=int(shared["plan_id"]),
            expected_target=target,
            require_active=require_active,
        )
    return deployment_qa_stage_subject(
        conn,
        run_id=str(execution["deployment_run_id"]),
        stage_name=str(execution["deployment_stage"]),
        member_item_id=execution.get("deployment_member_item_id"),
        require_active=require_active,
    )


def requirement_subject(
    conn: Any, requirement_id: int, *, require_active: bool = True
) -> dict:
    """Resolve stage policy and target authority from a stored requirement."""
    rows = query_rows(
        conn,
        "SELECT deployment_run_id,deployment_stage,deployment_member_item_id,execution_target_json "
        "FROM qa_requirements WHERE id=%s",
        (int(requirement_id),),
    )
    if not rows:
        raise ValueError(
            "shared_plan_requirement_missing: inspect the requirement id before retrying"
        )
    return execution_subject(conn, rows[0], require_active=require_active)


def group_members(conn: Any, subject: Mapping, target: Mapping) -> list[int]:
    """Only members selecting this exact plan/source/target receive its verdict."""
    members = query_rows(
        conn,
        "SELECT item_id FROM deployment_run_items WHERE run_id=%s ORDER BY item_id",
        (subject["id"],),
    )
    found = []
    for row in members:
        try:
            resolve_shared_subject(
                conn,
                run_id=subject["id"],
                stage_name=subject["stage"]["name"],
                plan_id=subject["shared_plan"]["plan_id"],
                member_item_id=int(row["item_id"]),
                expected_target=target,
                require_active=False,
            )
        except ValueError:
            continue
        found.append(int(row["item_id"]))
    return found


def member_group_digests(conn: Any, run_id: str, stage: str, member: int) -> set[str]:
    from yoke_core.domain.deployment_qa_stage_contract import (
        deployment_qa_stage_subject,
    )
    from yoke_core.domain.deployment_qa_execution_target import (
        deployment_qa_execution_target,
    )
    from yoke_core.domain.qa_execution_environment_target import target_digest

    subject = deployment_qa_stage_subject(
        conn,
        run_id=run_id,
        stage_name=stage,
        member_item_id=member,
        require_active=False,
    )
    target = deployment_qa_execution_target(conn, subject)
    return {
        target_digest(deployment_qa_execution_target(conn, group))
        for group in member_plan_subjects(conn, subject, target)
    }


def shared_target_identity(raw: Any) -> Mapping | None:
    """Recognize only explicit shared groups when reading run-wide history."""
    import json

    try:
        target = raw if isinstance(raw, Mapping) else json.loads(str(raw or "{}"))
    except (TypeError, ValueError):
        return None
    if not isinstance(target, Mapping):
        return None
    return (target.get("deployment") or {}).get("shared_plan")
