"""A later standing-plan publication cannot rewrite an older run's contract."""

import json

import pytest

from runtime.api.domain.test_installer_campaign_plan_sync import (
    source_checkout as source_checkout,
)
from runtime.api.domain.test_deployment_qa_stage_execution import (
    _plan,
    _seed_run,
    _stages,
    _complete_case,
)
from runtime.api.domain.test_deployment_qa_shared_plans import _attach
from yoke_core.domain import qa_plan_source_revision as source_binding
from yoke_core.domain.deployment_run_carried_work_source import LocalCheckoutSource
from yoke_core.domain.deployment_qa_stage_materialization import (
    materialize_deployment_qa_stage,
)
from yoke_core.domain.deployment_qa_run_acceptance import current_item_qa
from yoke_core.domain.deployment_requirement_snapshots import (
    snapshot_member_requirements,
    requirement_selection,
)
from yoke_core.domain.qa_plan_management import replace_plan_cases, QaPlanError
from yoke_core.domain.qa_plan_execution_state import begin_plan_execution
from yoke_core.domain.deploy_target_occupancy import open_qa_lines

RUN = "run-saved-contract"
MEMBERS = (9921, 9922)


def _materialize(conn, member=MEMBERS[0]):
    return materialize_deployment_qa_stage(
        conn,
        deployment_run_id=RUN,
        deployment_stage="item-qa",
        deployment_member_item_id=member,
    )


@pytest.fixture
def published(test_db, source_checkout, monkeypatch):
    root, git = source_checkout
    old = git(root, "rev-parse", "HEAD").stdout.strip()
    monkeypatch.setattr(
        source_binding,
        "open_carried_work_source",
        lambda conn, project_id: LocalCheckoutSource(str(root)),
    )
    pid = _plan(test_db)
    test_db.execute("UPDATE projects SET default_branch='stable' WHERE id=1")
    test_db.execute("UPDATE qa_plans SET source_revision=%s WHERE id=%s", (old, pid))
    stages = _stages(pid)
    stages[1].pop("cases")
    _seed_run(test_db, run_id=RUN, stages=stages, members=MEMBERS, release_lineage=old)
    for member in MEMBERS:
        _attach(test_db, member, pid)
    ids = _materialize(test_db)["created_requirement_ids"]
    # Older admission stored individual requirements, but no whole-plan array.
    row = dict(
        test_db.execute(
            "SELECT * FROM qa_requirements WHERE id=%s", (ids[0],)
        ).fetchone()
    )
    for member in MEMBERS:
        test_db.execute(
            "UPDATE deployment_run_items SET requirement_snapshot=%s WHERE run_id=%s AND item_id=%s",
            (
                json.dumps(
                    {"schema": 1, "plans": [], "requirements": [row]}, default=str
                ),
                RUN,
                member,
            ),
        )
    test_db.commit()
    (root / "cases.json").write_text('["new definitions"]\n')
    assert git(root, "commit", "-am", "Publish new definitions").returncode == 0
    new = git(root, "rev-parse", "HEAD").stdout.strip()
    assert git(root, "push", "origin", "stable").returncode == 0
    replace_plan_cases(
        test_db,
        plan_id=pid,
        source_revision=new,
        cases=[
            {
                "case_key": key,
                "method_id": "command",
                "instructions": "new instruction",
                "expected_outcome": "new outcome",
                "method_config": {"command": "false"},
            }
            for key in ("command-smoke", "added-check")
        ],
    )
    return pid, ids, old, new, row


def test_old_contract_survives_publication_without_writes(test_db, published):
    pid, ids, old, new, before = published
    for member in MEMBERS:
        result = _materialize(test_db, member)
        assert result["created_requirement_ids"] == []
        assert result["existing_requirement_ids"] == ids
        answer = current_item_qa(
            test_db, run_id=RUN, item_id=member, current_stage="item-qa"
        )
        assert not answer.accepted
    assert open_qa_lines(test_db, RUN)
    after = dict(
        test_db.execute(
            "SELECT * FROM qa_requirements WHERE id=%s", (ids[0],)
        ).fetchone()
    )
    assert after == before
    execution = begin_plan_execution(
        test_db,
        deployment_run_id=RUN,
        deployment_stage="item-qa",
        deployment_member_item_id=MEMBERS[0],
        actor_id="2",
        session_id="saved-contract",
    )
    assert [r["requirement_id"] for r in execution["roster"]] == ids
    _complete_case(test_db, execution)
    assert all(
        current_item_qa(
            test_db, run_id=RUN, item_id=m, current_stage="item-qa"
        ).accepted
        for m in MEMBERS
    )


def test_new_admission_freezes_current_definition(test_db, published):
    pid, ids, old, new, before = published
    stages = _stages(pid)
    stages[1].pop("cases")
    _seed_run(
        test_db,
        run_id="run-successor",
        stages=stages,
        members=(),
        existing_members=MEMBERS,
        release_lineage=new,
    )
    snapshot = json.loads(
        snapshot_member_requirements(
            test_db,
            run_id="run-successor",
            item_id=MEMBERS[0],
            selection_json=requirement_selection(),
        )
    )
    (plan,) = snapshot["plans"]
    assert plan["plan"]["source_revision"] == new
    assert [c["case_key"] for c in plan["cases"]] == ["command-smoke", "added-check"]
    with pytest.raises(QaPlanError, match="qa_plan_source_candidate_mismatch"):
        source_binding.require_candidate_plan(test_db, plan["plan"], RUN)
    result = materialize_deployment_qa_stage(
        test_db,
        deployment_run_id="run-successor",
        deployment_stage="item-qa",
        deployment_member_item_id=MEMBERS[0],
    )
    assert len(result["created_requirement_ids"]) == 2


def test_takeover_and_manual_removal_read_saved_contract(test_db, published):
    from runtime.api.fixtures.deployment_run_driver_fixture import release_seeded_driver
    from yoke_core.domain.deployment_runs_crud_mutate import cmd_remove_item
    from yoke_core.domain.deployment_run_target_takeover import (
        _waiting_run,
        _moving_members,
    )

    pid, ids, old, new, before = published
    test_db.execute(
        "UPDATE items SET status='release' WHERE id=ANY(%s)", (list(MEMBERS),)
    )
    test_db.commit()
    release_seeded_driver(test_db, RUN)
    new_run = dict(
        test_db.execute("SELECT * FROM deployment_runs WHERE id=%s", (RUN,)).fetchone()
    )
    new_run["id"] = "run-successor"
    waiting = _waiting_run(test_db, new_run)
    assert waiting["id"] == RUN
    assert [m["item_id"] for m in _moving_members(test_db, waiting, False)] == list(
        MEMBERS
    )
    message = cmd_remove_item(
        RUN, MEMBERS[1], reason="member rides successor", session_id="s", actor_id=1
    )
    assert "is not fully accepted" in message
    assert (
        dict(
            test_db.execute(
                "SELECT * FROM qa_requirements WHERE id=%s", (ids[0],)
            ).fetchone()
        )
        == before
    )


def test_baseline_variants_remain_distinct_and_ordered(test_db, published):
    from yoke_core.domain.deployment_qa_saved_plan_contract import saved_plan_contract
    from yoke_core.domain.deployment_qa_stage_contract import (
        deployment_qa_stage_subject,
    )
    from yoke_core.domain.deployment_qa_execution_target import (
        deployment_qa_execution_target,
    )

    pid, ids, old, new, before = published
    columns = [
        key for key in before if key not in ("id", "host_baseline", "baseline_position")
    ]
    listed = ",".join(columns)
    test_db.execute(
        "UPDATE qa_requirements SET host_baseline='fresh-host',baseline_position=1 WHERE id=%s",
        (ids[0],),
    )
    test_db.execute(
        f"INSERT INTO qa_requirements ({listed},host_baseline,baseline_position) "
        f"SELECT {listed},'shell-preconfigured',2 FROM qa_requirements WHERE id=%s",
        (ids[0],),
    )
    subject = deployment_qa_stage_subject(
        test_db, run_id=RUN, stage_name="item-qa", member_item_id=MEMBERS[0]
    )
    snapshot = saved_plan_contract(
        test_db, subject, deployment_qa_execution_target(test_db, subject), pid, []
    )
    assert [r["host_baseline"] for r in snapshot["materialized_requirements"]] == [
        "fresh-host",
        "shell-preconfigured",
    ]
    assert [c["case_key"] for c in snapshot["cases"]] == [
        "command-smoke",
        "command-smoke",
    ]


@pytest.mark.parametrize("damage", ["digest", "source", "missing"])
def test_invalid_historical_contract_refuses(test_db, published, damage):
    pid, ids, old, new, row = published
    if damage == "missing":
        test_db.execute("DELETE FROM qa_requirements WHERE id=%s", (ids[0],))
        reason = "qa_saved_plan_contract_missing"
    elif damage == "digest":
        test_db.execute(
            "UPDATE qa_requirements SET execution_target_digest='invalid' WHERE id=%s",
            (ids[0],),
        )
        reason = "qa_saved_plan_contract_invalid"
    else:
        from yoke_core.domain.qa_execution_environment_target import (
            canonical_target,
            target_digest,
        )

        target = json.loads(row["execution_target_json"])
        target["deployment"]["shared_plan"]["source_revision"] = new
        test_db.execute(
            "UPDATE qa_requirements SET execution_target_json=%s,execution_target_digest=%s WHERE id=%s",
            (canonical_target(target), target_digest(target), ids[0]),
        )
        reason = "qa_plan_source_candidate_mismatch"
    test_db.commit()
    with pytest.raises(QaPlanError, match=reason):
        _materialize(test_db)
