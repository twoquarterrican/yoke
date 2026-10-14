"""Already materialized member copies converge without rewriting a live roster."""

import pytest

from runtime.api.domain.test_deployment_qa_shared_plans import (
    RUN,
    MEMBERS,
    _seed,
    _materialize,
    _begin,
)
from runtime.api.domain.test_deployment_qa_stage_execution import _complete_case
from yoke_core.domain.deployment_qa_execution_target import (
    deployment_qa_execution_target,
)
from yoke_core.domain.deployment_qa_stage_contract import deployment_qa_stage_subject
from yoke_core.domain.deployment_qa_plan_selection import selected_plans
from yoke_core.domain.deployment_qa_subject_materialization import materialize_subject
from yoke_core.domain.deployment_qa_stage_materialization import (
    materialize_deployment_qa_stage,
)
from yoke_core.domain.qa_plan_execution_state import (
    begin_plan_execution,
    finish_plan_execution,
)
from yoke_core.domain.deployment_qa_stage_gate import deployment_qa_stage_status
from yoke_core.domain.qa_plan_management import QaPlanError


def _member_copies(conn):
    ids = []
    for member in MEMBERS:
        subject = deployment_qa_stage_subject(
            conn,
            run_id=RUN,
            stage_name="item-qa",
            member_item_id=member,
        )
        target = deployment_qa_execution_target(conn, subject)
        snapshots = selected_plans(
            conn, subject, target=target, admitted=[], agent_plan=None
        )
        result = materialize_subject(
            conn,
            subject=subject,
            target=target,
            snapshots=snapshots,
            admitted=[],
        )
        ids.extend(result["created_requirement_ids"])
    return ids


def test_existing_member_copies_retire_and_one_shared_execution_credits_both(test_db):
    _seed(test_db)
    previous = _member_copies(test_db)
    from yoke_core.domain.deployment_qa_stage_gate import _acceptance_requirement

    for member in MEMBERS:
        subject = deployment_qa_stage_subject(
            test_db, run_id=RUN, stage_name="item-qa", member_item_id=member
        )
        previous.append(
            _acceptance_requirement(
                test_db,
                subject=subject,
                target=deployment_qa_execution_target(test_db, subject),
            )
        )
    test_db.commit()
    materialized = _materialize(test_db, MEMBERS[0])
    assert len(materialized["created_requirement_ids"]) == 1
    retired = test_db.execute(
        "SELECT id,retracted_at,retraction_source FROM qa_requirements WHERE id=ANY(%s)",
        (previous,),
    ).fetchall()
    assert all(
        row["retracted_at"] and row["retraction_source"] == "shared_plan_group"
        for row in retired
    )
    execution = _begin(test_db, MEMBERS[1])
    _complete_case(test_db, execution)
    for member in MEMBERS:
        assert deployment_qa_stage_status(
            test_db,
            run_id=RUN,
            stage_name="item-qa",
            member_item_id=member,
        )["accepted"]


def test_live_member_copy_refuses_conversion_without_partial_retirement(test_db):
    _seed(test_db)
    previous = _member_copies(test_db)
    execution = begin_plan_execution.__wrapped__(
        test_db,
        deployment_run_id=RUN,
        deployment_stage="item-qa",
        deployment_member_item_id=MEMBERS[0],
        actor_id="2",
        session_id="member-copy",
    )
    with pytest.raises(QaPlanError, match="shared_plan_duplicate_execution_live"):
        materialize_deployment_qa_stage(
            test_db,
            deployment_run_id=RUN,
            deployment_stage="item-qa",
            deployment_member_item_id=MEMBERS[1],
        )
    rows = test_db.execute(
        "SELECT id,retracted_at FROM qa_requirements WHERE deployment_run_id=%s",
        (RUN,),
    ).fetchall()
    assert {row["id"] for row in rows} == set(previous)
    assert not any(row["retracted_at"] for row in rows)
    finish_plan_execution(
        test_db, execution, state="aborted", reason="owner stops old roster"
    )
    assert len(_materialize(test_db, MEMBERS[1])["created_requirement_ids"]) == 1


def test_member_source_obligations_read_the_same_shared_verdict(test_db, monkeypatch):
    from runtime.api.domain.test_deployment_qa_admission_execution import (
        _original_requirement,
    )
    from yoke_core.domain import deployment_qa_source_obligation as source_authority

    plan_id = _seed(test_db)
    sources = []
    for member in MEMBERS:
        source = _original_requirement(test_db, item_id=member, method_id="command")
        test_db.execute(
            "UPDATE qa_requirements SET qa_kind='plan_case',plan_id=%s,plan_case_key='command-smoke' WHERE id=%s",
            (plan_id, source),
        )
        sources.append(source)
    test_db.commit()
    _materialize(test_db, MEMBERS[0])
    _complete_case(test_db, _begin(test_db, MEMBERS[0]))
    monkeypatch.setattr(
        source_authority,
        "latest_qa_member_run",
        lambda *args, **kwargs: {"id": RUN, "status": "succeeded"},
    )
    assert all(
        source_authority.source_obligation_consumed(
            test_db,
            item_id=member,
            source_requirement_id=source,
        )
        for member, source in zip(MEMBERS, sources, strict=True)
    )
