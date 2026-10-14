"""Plan selection and explicit phase attachments have separate obligations."""

import pytest

from runtime.api.domain.test_item_posture_amend import _dash, _plan, REVIEW
from runtime.api.fixtures.backlog_inserts import insert_qa_run
from yoke_core.domain.dash_posture_verification_gate import verification_gate
from yoke_core.domain.item_posture_bindings import bind_item_posture_selection
from yoke_core.domain.qa_plan_attachment_retract import retract_plan_from_item
from yoke_core.domain.qa_plan_attachments import (
    attach_plan_to_item,
    materialize_for_item,
)
from yoke_core.domain.qa_plan_management import QaPlanError


@pytest.mark.parametrize("commit", [True, False])
def test_plan_selection_never_attaches_or_creates_review_gate(test_db, commit):
    plan = _plan(test_db, "selection-only")
    selection = {"kind": "plan", "plan_id": plan["id"]}
    item_id = _dash(test_db, item_id=2850, posture={"verification": selection})
    assert bind_item_posture_selection(
        test_db,
        item_id=item_id,
        definition={},
        posture={"verification": selection},
        actor_id=None,
        commit=commit,
    ) == {"verification": None}
    assert (
        test_db.execute(
            "SELECT 1 FROM qa_plan_item_attachments WHERE item_id=%s", (item_id,)
        ).fetchone()
        is None
    )
    assert (
        verification_gate(
            test_db,
            item_id=item_id,
            verification=selection,
            target_status=REVIEW,
        )
        is None
    )
    attach_plan_to_item(
        test_db,
        item_id=item_id,
        plan_id=plan["id"],
        transition_id=REVIEW,
        qa_phase="verification",
    )
    assert (
        verification_gate(
            test_db,
            item_id=item_id,
            verification=selection,
            target_status=REVIEW,
        )["error_code"]
        == "GATE_DASH_VERIFICATION_REQUIRED"
    )
    retract_plan_from_item(
        test_db,
        item_id=item_id,
        plan_id=plan["id"],
        transition_id=REVIEW,
        reason="wrong review binding",
    )
    attach_plan_to_item(
        test_db,
        item_id=item_id,
        plan_id=plan["id"],
        transition_id="release",
        qa_phase="post_deploy",
    )
    materialize_for_item(test_db, item_id=item_id, transition_id="release")
    assert (
        verification_gate(
            test_db,
            item_id=item_id,
            verification=selection,
            target_status=REVIEW,
        )
        is None
    )
    assert (
        verification_gate(
            test_db,
            item_id=item_id,
            verification=selection,
            target_status="done",
        )["error_code"]
        == "GATE_DASH_VERIFICATION_UNSATISFIED"
    )


@pytest.mark.parametrize(
    "phase,transition",
    [
        ("verification", REVIEW),
        ("post_deploy", "release"),
        ("manual_acceptance", "done"),
    ],
)
@pytest.mark.parametrize("verdict", [None, "pending", "fail", "pass"])
def test_retraction_at_any_phase_requires_no_recorded_run(
    test_db, phase, transition, verdict
):
    plan = _plan(test_db, "retraction-before-run")
    item_id = _dash(
        test_db,
        item_id=2851,
        posture={
            "verification": {"kind": "plan", "plan_id": plan["id"]},
        },
    )
    attach_plan_to_item(
        test_db,
        item_id=item_id,
        plan_id=plan["id"],
        transition_id=transition,
        qa_phase=phase,
    )
    requirement_id = materialize_for_item(
        test_db,
        item_id=item_id,
        transition_id=transition,
    )["created_requirement_ids"][0]
    if verdict is not None:
        insert_qa_run(
            test_db,
            qa_requirement_id=requirement_id,
            verdict=None if verdict == "pending" else verdict,
        )
        with pytest.raises(QaPlanError, match="attachment_has_recorded_run"):
            retract_plan_from_item(
                test_db,
                item_id=item_id,
                plan_id=plan["id"],
                transition_id=transition,
                reason="wrong attachment",
            )
        assert (
            test_db.execute(
                "SELECT retracted_at FROM qa_requirements WHERE id=%s",
                (requirement_id,),
            ).fetchone()[0]
            is None
        )
    else:
        receipt = retract_plan_from_item(
            test_db,
            item_id=item_id,
            plan_id=plan["id"],
            transition_id=transition,
            reason="wrong attachment",
        )
        assert receipt["retired_requirement_ids"] == [requirement_id]
        assert (
            materialize_for_item(
                test_db,
                item_id=item_id,
                transition_id=transition,
            )["created_requirement_ids"]
            == []
        )
        assert (
            test_db.execute(
                "SELECT retracted_at FROM qa_requirements WHERE id=%s",
                (requirement_id,),
            ).fetchone()[0]
            is not None
        )
