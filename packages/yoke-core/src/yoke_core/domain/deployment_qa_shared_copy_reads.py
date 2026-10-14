"""Reach a member's shared copies, including a withdrawn attachment's history."""

import json
from collections.abc import Mapping

from yoke_core.domain.db_helpers import query_rows
from yoke_core.domain.deployment_qa_shared_plans import (
    member_group_digests,
    shared_subject,
    shared_target_identity,
)
from yoke_core.domain.qa_execution_environment_target import canonical_target
from yoke_core.domain.qa_obligation_settlement import settled_obligation_sql


def member_owns_shared_copy(conn, row, member, *, include_withdrawn=False):
    raw = row["execution_target_json"]
    shared = shared_target_identity(raw)
    if not shared:
        return False
    if row["execution_target_digest"] in member_group_digests(
        conn,
        row["deployment_run_id"],
        row["deployment_stage"],
        member,
    ):
        return True
    if not include_withdrawn:
        return False
    from yoke_core.domain.qa_plan_attachment_reads import retracted_item_plan_ids

    if int(shared["plan_id"]) not in retracted_item_plan_ids(conn, member):
        return False
    from yoke_core.domain.deployment_qa_stage_contract import (
        deployment_qa_stage_subject,
    )
    from yoke_core.domain.deployment_qa_execution_target import (
        deployment_qa_execution_target,
    )

    subject = deployment_qa_stage_subject(
        conn,
        run_id=row["deployment_run_id"],
        stage_name=row["deployment_stage"],
        member_item_id=member,
        require_active=False,
    )
    target = raw if isinstance(raw, Mapping) else json.loads(str(raw))
    snapshot = {
        "plan": {
            "id": shared["plan_id"],
            "source_revision": shared.get("source_revision"),
        }
    }
    group = shared_subject(
        subject, deployment_qa_execution_target(conn, subject), snapshot
    )
    return canonical_target(
        deployment_qa_execution_target(conn, group)
    ) == canonical_target(target)


def shared_plan_copies(conn, member, plan_id, *, include_withdrawn=False):
    rows = query_rows(
        conn,
        "SELECT q.id,q.plan_id,q.retracted_at,q.waived_at,q.superseded_by_requirement_id,q.execution_target_json,"
        "q.execution_target_digest,q.deployment_run_id,q.deployment_stage,"
        "q.deployment_member_item_id FROM qa_requirements q "
        "JOIN deployment_run_items m ON m.run_id=q.deployment_run_id AND m.item_id=%s "
        "WHERE q.plan_id=%s AND q.deployment_member_item_id IS NULL ORDER BY q.id",
        (member, plan_id),
    )
    return [
        dict(row)
        for row in rows
        if member_owns_shared_copy(
            conn,
            row,
            member,
            include_withdrawn=include_withdrawn,
        )
    ]


def withdrawn_member_discharge(conn, subject, target):
    """An admitted group withdrawn by this member is no longer its obligation."""
    member = subject.get("member_item_id")
    if member is None:
        return False
    from yoke_core.domain.deployment_qa_shared_plans import member_plan_subjects
    from yoke_core.domain.qa_plan_attachment_reads import retracted_item_plan_ids

    withdrawn = retracted_item_plan_ids(conn, member)
    if not withdrawn or member_plan_subjects(conn, subject, target):
        return False
    private = conn.execute(
        "SELECT 1 FROM qa_requirements q WHERE q.deployment_run_id=%s AND q.deployment_stage=%s "
        "AND q.deployment_member_item_id=%s AND q.qa_kind<>'deployment_stage_acceptance' "
        f"AND NOT {settled_obligation_sql(conn, 'q')} LIMIT 1",
        (subject["id"], subject["stage"]["name"], member),
    ).fetchone()
    if private:
        return False
    from yoke_core.domain.qa_obligation_settlement import obligation_settled
    from yoke_core.domain.deployment_qa_shared_plans import group_members

    copies = [
        row
        for plan in withdrawn
        for row in shared_plan_copies(conn, member, plan, include_withdrawn=True)
        if row["deployment_run_id"] == subject["id"]
        and row["deployment_stage"] == subject["stage"]["name"]
    ]
    for row in copies:
        if obligation_settled(row):
            continue
        raw = row["execution_target_json"]
        stored = raw if isinstance(raw, Mapping) else json.loads(str(raw))
        group = {**subject, "shared_plan": shared_target_identity(stored)}
        if not any(other != member for other in group_members(conn, group, stored)):
            return False
    return bool(copies)
