"""Shared-plan groups form only from shared attachments and read only their own rows."""

from runtime.api.domain.test_deployment_qa_shared_plans import (
    MEMBERS,
    RUN,
    _attach,
    _begin,
    _materialize,
    _seed,
)
from runtime.api.domain.test_deployment_qa_stage_execution import (
    _complete_case,
    _plan,
    _seed_run,
    _stages,
)
from yoke_core.domain.deployment_qa_execution_target import (
    deployment_qa_execution_target,
)
from yoke_core.domain.deployment_qa_shared_plans import (
    member_plan_subjects,
    requirement_subject,
)
from yoke_core.domain.deployment_qa_stage_case_failures import (
    NO_CASES_FAILURE,
    case_failures,
)
from yoke_core.domain.deployment_qa_stage_contract import deployment_qa_stage_subject
from yoke_core.domain.deployment_qa_stage_gate import deployment_qa_stage_status
from yoke_core.domain.qa_execution_environment_target import target_digest


def test_unmaterialized_group_does_not_borrow_another_groups_memberless_rows(
    test_db,
):
    shared_plan = _seed(test_db)
    shared_rows = _materialize(test_db, MEMBERS[0])["created_requirement_ids"]
    assert shared_rows
    other_plan = _plan(test_db, "other-plan")
    for member in MEMBERS:
        _attach(test_db, member, other_plan)
    subject = deployment_qa_stage_subject(
        test_db, run_id=RUN, stage_name="item-qa", member_item_id=MEMBERS[1]
    )
    groups = {
        group["shared_plan"]["plan_id"]: group
        for group in member_plan_subjects(
            test_db, subject, deployment_qa_execution_target(test_db, subject)
        )
    }
    assert set(groups) == {shared_plan, other_plan}

    def failures(plan_id):
        group = groups[plan_id]
        return case_failures(
            test_db,
            run_id=RUN,
            stage_name="item-qa",
            member_item_id=None,
            execution_target_digest=target_digest(
                deployment_qa_execution_target(test_db, group)
            ),
            shared_plan_id=plan_id,
        )

    assert failures(other_plan) == [NO_CASES_FAILURE]
    assert {failure.requirement_id for failure in failures(shared_plan)} == set(
        shared_rows
    )

    status = deployment_qa_stage_status(
        test_db, run_id=RUN, stage_name="item-qa", member_item_id=MEMBERS[1]
    )
    assert status["accepted"] is False
    named = " ".join(str(reason) for reason in status.get("reasons") or [])
    assert "None" not in named


def test_plan_attached_by_one_member_stays_that_members_private_copy(test_db):
    single = _plan(test_db)
    stages = _stages(single)
    stages[1].pop("cases")
    _seed_run(test_db, run_id=RUN, stages=stages, members=MEMBERS)
    _attach(test_db, MEMBERS[1], single)
    (requirement_id,) = _materialize(test_db, MEMBERS[1])["created_requirement_ids"]
    owner = test_db.execute(
        "SELECT deployment_member_item_id FROM qa_requirements WHERE id=%s",
        (requirement_id,),
    ).fetchone()[0]
    assert owner == MEMBERS[1]
    subject = requirement_subject(test_db, requirement_id)
    assert subject["member_item_id"] == MEMBERS[1]
    assert subject["stage"]["scope"] == "item"

    execution = _begin(test_db, MEMBERS[1])
    assert execution["deployment_member_item_id"] == MEMBERS[1]
    assert _complete_case(test_db, execution) == requirement_id
    assert deployment_qa_stage_status(
        test_db, run_id=RUN, stage_name="item-qa", member_item_id=MEMBERS[1]
    )["accepted"]
