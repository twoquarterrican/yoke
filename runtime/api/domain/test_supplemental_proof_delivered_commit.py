"""Stage proof on the commit production delivered is credited at close-out.

A hosted production release pins one item-project commit and then delivers
another (its promotion commits a version pin on top). A stage run created
afterwards records and proves the delivered commit. Close-out, holder
coverage, and the add-item warning all accept the final run's pinned or
delivered commit, and still refuse an unrelated one.
"""

import json

import pytest

from runtime.api.domain.test_release_member_target_enrollment import _pair
from yoke_core.domain.deployment_item_completion_runs import (
    latest_qa_member_run,
    uncredited_supplemental_notice,
)
from yoke_core.domain.deployment_run_member_targeting import holder_covers_run
from yoke_core.domain.deployment_runs_crud_mutate import cmd_add_item

PINNED = "a" * 40
DELIVERED = "b" * 40
UNRELATED = "c" * 40


def _carrier_production(conn, *, item_id: int) -> None:
    """Make run-prod another project's release that pinned and delivered."""
    _pair(conn, item_id=item_id)
    conn.execute(
        "INSERT INTO projects(id,slug,name,github_repo,public_item_prefix,org_id,"
        "created_at) VALUES (2,'carrier','Carrier','upyoke/carrier','CAR',1,"
        "'2026-01-01T00:00:00Z') ON CONFLICT(id) DO NOTHING"
    )
    sources = {
        "schema": 1,
        "inputs": {},
        "projects": [
            {
                "project_id": 1,
                "commit_sha": PINNED,
                "outputs": [
                    {
                        "commit_sha": DELIVERED,
                        "reason": "release_pin_materialization",
                    }
                ],
            }
        ],
    }
    conn.execute(
        "UPDATE deployment_runs SET project_id=2,release_lineage=%s,"
        "bound_sources=%s,status='succeeded' WHERE id='run-prod'",
        ("d" * 40, json.dumps(sources)),
    )
    conn.commit()


def _stage_on(conn, sha: str) -> None:
    conn.execute(
        "UPDATE deployment_runs SET release_lineage=%s,status='succeeded' "
        "WHERE id='run-stage'",
        (sha,),
    )
    conn.commit()


@pytest.mark.parametrize(
    ("stage_sha", "credited"),
    [(DELIVERED, True), (PINNED, True), (UNRELATED, False)],
)
def test_close_out_and_holder_coverage_agree_on_creditable_stage_commit(
    test_db, stage_sha, credited
):
    item_id = 9790
    _carrier_production(test_db, item_id=item_id)
    _stage_on(test_db, stage_sha)

    member = latest_qa_member_run(test_db, item_id=item_id, target_env="stage")
    assert (member is not None and member["id"] == "run-stage") is credited
    # A production holder answers for a stage run only when stage proof on
    # that commit would go uncredited.
    assert (
        holder_covers_run(
            test_db, holder_id="run-prod", run_id="run-stage", item_id=item_id
        )
        is not credited
    )
    notice = uncredited_supplemental_notice(
        test_db, run_id="run-stage", item_id=item_id
    )
    assert (notice == "") is credited


def test_add_item_warns_when_stage_proof_will_not_be_credited(test_db):
    item_id = 9791
    _carrier_production(test_db, item_id=item_id)
    for run_id, sha in (
        ("run-stage-unrelated", UNRELATED),
        ("run-stage-ok", DELIVERED),
    ):
        test_db.execute(
            "INSERT INTO deployment_runs(id,project_id,flow,release_lineage,status,"
            "created_at,target_tier,target_environment_id) "
            "SELECT %s,project_id,flow,%s,'created',created_at,target_tier,"
            "target_environment_id FROM deployment_runs WHERE id='run-stage'",
            (run_id, sha),
        )
    test_db.commit()

    warned = cmd_add_item("run-stage-unrelated", item_id)
    assert "supplemental_proof_not_credited" in warned
    assert UNRELATED in warned and DELIVERED in warned and PINNED in warned
    assert "yoke deployment-runs remove-item run-stage-unrelated" in warned
    assert "supplemental_proof_not_credited" not in cmd_add_item(
        "run-stage-ok", item_id
    )
