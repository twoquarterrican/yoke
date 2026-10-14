"""A shared-plan group's case lookup never reads another group's memberless rows."""

from runtime.api.domain.test_deployment_qa_shared_plans import (
    MEMBERS,
    RUN,
    _attach,
    _materialize,
    _seed,
)
from runtime.api.domain.test_deployment_qa_stage_execution import _plan
from yoke_core.domain.deployment_qa_execution_target import (
    deployment_qa_execution_target,
)
from yoke_core.domain.deployment_qa_shared_plans import member_plan_subjects
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
    other_plan = _plan(test_db, "other-plan")
    _attach(test_db, MEMBERS[1], other_plan)
    shared_rows = _materialize(test_db, MEMBERS[0])["created_requirement_ids"]
    assert shared_rows
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
