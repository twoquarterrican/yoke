"""Member acceptance is the conjunction of its own private and shared subjects."""

from yoke_core.domain.qa_obligation_settlement import settled_obligation_sql
from yoke_core.domain.deployment_qa_shared_plans import member_plan_subjects
from yoke_core.domain.deployment_qa_execution_target import (
    deployment_qa_execution_target,
)


def acceptance_subjects(conn, subject, target):
    if subject.get("shared_plans_resolved"):
        return []
    groups = member_plan_subjects(conn, subject, target)
    if not groups:
        return []
    private = conn.execute(
        "SELECT 1 FROM qa_requirements WHERE deployment_run_id=%s AND deployment_stage=%s "
        "AND deployment_member_item_id=%s "
        f"AND NOT {settled_obligation_sql(conn)} "
        "AND qa_kind<>'deployment_stage_acceptance' LIMIT 1",
        (subject["id"], subject["stage"]["name"], subject["member_item_id"]),
    ).fetchone()
    subjects = [
        (group, deployment_qa_execution_target(conn, group)) for group in groups
    ]
    if private:
        subjects.append(({**subject, "shared_plans_resolved": True}, target))
    return subjects


def shared_member_acceptance(conn, subject, target, acceptance_qa_kind):
    from yoke_core.domain.deployment_qa_stage_acceptance import (
        StageAcceptance,
        STAGE_ACCEPTED,
        stage_acceptance,
    )

    subjects = acceptance_subjects(conn, subject, target)
    if not subjects:
        from yoke_core.domain.deployment_qa_shared_copy_reads import (
            withdrawn_member_discharge,
        )
        from yoke_core.domain.deployment_qa_stage_acceptance import STAGE_DISCHARGED

        return (
            StageAcceptance(STAGE_DISCHARGED, ())
            if withdrawn_member_discharge(conn, subject, target)
            else None
        )
    answers = [
        stage_acceptance(
            conn,
            subject=part,
            target=part_target,
            acceptance_qa_kind=acceptance_qa_kind,
        )
        for part, part_target in subjects
    ]
    unresolved = [answer for answer in answers if not answer.accepted]
    return StageAcceptance(
        unresolved[0].state if unresolved else STAGE_ACCEPTED,
        tuple(reason for answer in unresolved for reason in answer.blockers),
        tuple(rid for answer in unresolved for rid in answer.failed_requirement_ids),
    )


def shared_member_status(conn, subject, target):
    from yoke_core.domain.deployment_qa_stage_gate import _settle_stage_status
    from yoke_core.domain.deployment_qa_stage_outcome import passed

    subjects = acceptance_subjects(conn, subject, target)
    if not subjects:
        from yoke_core.domain.deployment_qa_shared_copy_reads import (
            withdrawn_member_discharge,
        )
        from yoke_core.domain.deployment_qa_stage_outcome import discharged

        return (
            discharged() if withdrawn_member_discharge(conn, subject, target) else None
        )
    answers = [
        _settle_stage_status(
            conn,
            subject=part,
            target=part_target,
            run_id=part["id"],
            stage_name=part["stage"]["name"],
            member_item_id=part.get("member_item_id"),
        )
        for part, part_target in subjects
    ]
    unresolved = [answer for answer in answers if not answer["accepted"]]
    if not unresolved:
        return passed()
    red = next(
        (
            answer
            for answer in unresolved
            if answer["outcome"] in {"blocked", "rejected"}
        ),
        unresolved[0],
    )
    return {
        **red,
        "reasons": [reason for answer in unresolved for reason in answer["reasons"]],
        "case_failures": [
            case for answer in unresolved for case in answer["case_failures"]
        ],
    }


def prior_shared_acceptance(conn, run_id, stage, member):
    from yoke_core.domain.deployment_qa_stage_contract import (
        deployment_qa_stage_subject,
    )
    from yoke_core.domain.deployment_qa_stage_acceptance import stage_acceptance

    if member is None:
        return None
    subject = deployment_qa_stage_subject(
        conn,
        run_id=run_id,
        stage_name=stage["name"],
        member_item_id=member,
        require_active=False,
    )
    target = deployment_qa_execution_target(conn, subject)
    if not member_plan_subjects(conn, subject, target):
        return None
    answer = stage_acceptance(
        conn,
        subject=subject,
        target=target,
        acceptance_qa_kind="deployment_stage_acceptance",
    )
    return [f"stage {stage['name']!r}: {reason}" for reason in answer.blockers]


def settle_shared_group(conn, subject, target):
    from yoke_core.domain.deployment_qa_stage_gate import _settle_stage_status
    from yoke_core.domain.deployment_qa_stage_settlement import settle_subject
    from yoke_core.domain.deployment_qa_shared_plans import group_members

    status = _settle_stage_status(
        conn,
        subject=subject,
        target=target,
        run_id=subject["id"],
        stage_name=subject["stage"]["name"],
        member_item_id=None,
    )
    conn.commit()
    for member in group_members(conn, subject, target):
        settle_subject(
            conn, run_id=subject["id"], stage=subject["stage"]["name"], member=member
        )
    return status
