"""Activation is observed: the checklist's last row reads the project's items."""

from __future__ import annotations

import pytest

from runtime.api.fixtures.backlog_inserts import insert_item
from yoke_contracts.onboard_checklist import (
    BRANCH_LOCAL_CHECKOUT,
    FIRST_ITEM_DONE_ROW_ID,
    STATUS_DEFERRED,
    STATUS_UNKNOWN,
    STATUS_VERIFIED,
)
from yoke_core.domain.project_onboarding_run_records import ProjectOnboardingRunError
from yoke_core.domain.project_onboarding_runs import get_run, init_run, update_run


def _first_item_row(conn, run_id):
    rows = get_run(run_id, conn=conn)["rows"]
    return next(row for row in rows if row["row_id"] == FIRST_ITEM_DONE_ROW_ID)


def _seed_run(conn, run_id):
    init_run(conn=conn, run_id=run_id, project_id=1, branch=BRANCH_LOCAL_CHECKOUT)


def test_open_work_leaves_activation_pending_with_the_steering_route(test_db):
    insert_item(test_db, id=41, status="implementing", workflow_id="dash")
    _seed_run(test_db, "first-pending")
    row = _first_item_row(test_db, "first-pending")
    assert row["status"] == STATUS_UNKNOWN
    assert row["reason"] == "first_item_not_done"
    assert "/yoke steer CURRENT-PLAN" in row["recovery"]


def test_first_done_item_verifies_activation_by_its_public_ref(test_db):
    insert_item(
        test_db, id=41, title="First outcome", status="done", workflow_id="dash"
    )
    insert_item(
        test_db, id=42, title="Later outcome", status="done", workflow_id="dash"
    )
    _seed_run(test_db, "first-done")
    row = _first_item_row(test_db, "first-done")
    assert row["status"] == STATUS_VERIFIED
    assert row["evidence"]["public_ref"].endswith("-41")
    assert row["evidence"]["title"] == "First outcome"


def test_finished_work_never_reopens_the_confirmed_profile(test_db):
    _seed_run(test_db, "first-profile")
    update_run(
        run_id="first-profile",
        project_id=1,
        conn=test_db,
        metadata={"execution_profile": {"delivery": "merge-only"}},
    )
    assert get_run("first-profile", conn=test_db)["profile_changed"] is False
    insert_item(test_db, id=41, status="done", workflow_id="dash")
    assert get_run("first-profile", conn=test_db)["profile_changed"] is False


@pytest.mark.parametrize("status", [STATUS_VERIFIED, STATUS_DEFERRED])
def test_activation_cannot_be_written_by_hand(test_db, status):
    _seed_run(test_db, "first-written")
    with pytest.raises(ProjectOnboardingRunError, match="onboarding_row_observed"):
        update_run(
            run_id="first-written",
            project_id=1,
            conn=test_db,
            row_status={FIRST_ITEM_DONE_ROW_ID: status},
        )
