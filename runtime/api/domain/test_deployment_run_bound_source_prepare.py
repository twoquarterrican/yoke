"""Unused consumer sources refresh without changing an already consumed input."""

from __future__ import annotations
import json
from typing import Any
from pathlib import Path
import pytest
from runtime.api.fixtures.bound_source_release import (
    CONSUMER_PROJECT,
    CONSUMER_ITEM_ID,
    two_project_release,
)
from runtime.api.fixtures.carried_release_candidate import (
    git,
    record_landing_receipt,
    item_ref,
)
from runtime.api.fixtures.backlog_inserts import insert_item
from yoke_core.domain.deployment_run_bound_sources import (
    record_bound_sources,
    parse_bound_sources,
    copy_bound_sources,
)
from yoke_core.domain.deployment_run_bound_source_prepare import prepare_bound_sources
from yoke_core.domain.deployment_runs_validation import cmd_validate_composition
from yoke_core.domain.deployment_run_composition_freeze import freeze_run_composition
from yoke_core.domain.deployment_run_stale_bound_sources import (
    check_bound_sources_current,
)


@pytest.fixture(autouse=True)
def dispatch_intent_schema(test_db):
    from yoke_core.domain.github_workflow_dispatch_intents import (
        GITHUB_WORKFLOW_DISPATCH_INTENTS_CREATE_SQL,
    )

    test_db.execute(GITHUB_WORKFLOW_DISPATCH_INTENTS_CREATE_SQL)
    test_db.commit()


def _record(conn: Any) -> dict:
    return parse_bound_sources(
        conn.execute(
            "SELECT bound_sources FROM deployment_runs WHERE id='run-candidate'"
        ).fetchone()[0]
    )


def _move(release: dict) -> str:
    git(
        release["consumer_repo"],
        "commit",
        "--allow-empty",
        "-m",
        "Consumer main advances",
    )
    return git(release["consumer_repo"], "rev-parse", "HEAD").strip()


def test_unused_consumer_moves_between_creation_and_dispatch(
    test_db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = two_project_release(test_db, tmp_path, monkeypatch)
    record_bound_sources(test_db, "run-candidate")
    current = _move(release)
    result = prepare_bound_sources(test_db, "run-candidate", "hosted-release")
    test_db.commit()
    entry = _record(test_db)["projects"][0]
    assert entry["commit_sha"] == current
    assert result["bound_sources"]["inputs"] == {"consumer_sha": current}
    assert entry["rebindings"][0]["from_sha"] == release["consumer_tip"]
    assert entry["rebindings"][0]["to_sha"] == current
    assert entry["consumed_by"] == "hosted-release"
    assert check_bound_sources_current(test_db, "run-candidate") == ([], "")
    carried = json.loads(
        test_db.execute(
            "SELECT carried_work FROM deployment_runs WHERE id='run-candidate'"
        ).fetchone()[0]
    )
    assert carried["bound_projects"][0]["derivation"]["release_lineage"] == current


def test_consumer_moving_after_consumption_still_refuses(
    test_db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = two_project_release(test_db, tmp_path, monkeypatch)
    record_bound_sources(test_db, "run-candidate")
    prepare_bound_sources(test_db, "run-candidate", "hosted-release")
    test_db.commit()
    before = _record(test_db)
    _move(release)
    with pytest.raises(ValueError, match="create a new run"):
        prepare_bound_sources(test_db, "run-candidate", "hosted-release")
    test_db.rollback()
    assert _record(test_db) == before


def test_refresh_after_unrelated_stage_admits_new_member_and_preserves_snapshots(
    test_db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = two_project_release(test_db, tmp_path, monkeypatch)
    record_bound_sources(test_db, "run-candidate")
    assert cmd_validate_composition("run-candidate", connection=test_db)[0]
    from yoke_core.domain.deployment_run_contained_items import (
        candidate_containment_basis,
        attest_candidate_containment,
        record_attested_candidate_containment,
    )

    from yoke_contracts.timestamps import utc_now

    test_db.execute(
        "UPDATE items SET merged_at=%s WHERE id=%s", (utc_now(), CONSUMER_ITEM_ID)
    )
    basis = candidate_containment_basis(test_db, "run-candidate")
    attested = attest_candidate_containment(
        basis,
        lambda project: str(
            release["consumer_repo"]
            if project == CONSUMER_PROJECT
            else release["carrier_repo"]
        ),
    )
    record_attested_candidate_containment(test_db, "run-candidate", attested)
    freeze_run_composition(test_db, "run-candidate")
    test_db.execute(
        "UPDATE deployment_runs SET status='executing' WHERE id='run-candidate'"
    )
    before = test_db.execute(
        "SELECT requirement_snapshot FROM deployment_run_items WHERE run_id='run-candidate' AND item_id=%s",
        (CONSUMER_ITEM_ID,),
    ).fetchone()[0]
    test_db.commit()
    insert_item(
        test_db,
        id=9699,
        project_sequence=9699,
        project=CONSUMER_PROJECT,
        workflow_id="blitz",
        status="implementing",
        deployment_flow="consumer-release-flow",
    )
    ref = item_ref(test_db, 9699)
    git(
        release["consumer_repo"],
        "commit",
        "--allow-empty",
        "-m",
        ref + " merged consumer work",
    )
    current = git(release["consumer_repo"], "rev-parse", "HEAD").strip()
    record_landing_receipt(test_db, 9699, branch=ref, tip=current)
    test_db.execute("UPDATE items SET merged_at=%s WHERE id=9699", (utc_now(),))
    test_db.commit()
    prepare_bound_sources(test_db, "run-candidate", "hosted-release")
    test_db.commit()
    members = test_db.execute(
        "SELECT item_id,requirement_snapshot FROM deployment_run_items WHERE run_id='run-candidate' ORDER BY item_id"
    ).fetchall()
    by_id = {int(r[0]): r[1] for r in members}
    assert 9699 in by_id and by_id[9699]
    assert by_id[CONSUMER_ITEM_ID] == before
    assert _record(test_db)["inputs"]["consumer_sha"] == current
    containment = json.loads(
        test_db.execute(
            "SELECT candidate_containment FROM deployment_runs WHERE id='run-candidate'"
        ).fetchone()[0]
    )
    consumer_answers = [
        a for a in containment["answers"] if a["project_id"] == release["consumer_id"]
    ]
    assert consumer_answers and all(
        a["candidate_lineage"] == current for a in consumer_answers
    )


def test_retry_copies_consumption_and_cannot_rebind(
    test_db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = two_project_release(test_db, tmp_path, monkeypatch)
    record_bound_sources(test_db, "run-candidate")
    prepare_bound_sources(test_db, "run-candidate", "hosted-release")
    copy_bound_sources(test_db, "run-candidate", "run-previous")
    test_db.execute(
        "UPDATE deployment_runs SET status='created' WHERE id='run-previous'"
    )
    test_db.commit()
    _move(release)
    with pytest.raises(ValueError, match="create a new run"):
        prepare_bound_sources(test_db, "run-previous", "hosted-release")
    test_db.rollback()


def test_preparation_is_idempotent_without_another_branch_move(
    test_db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = two_project_release(test_db, tmp_path, monkeypatch)
    record_bound_sources(test_db, "run-candidate")
    _move(release)
    prepare_bound_sources(test_db, "run-candidate", "hosted-release")
    test_db.commit()
    before = _record(test_db)
    assert (
        prepare_bound_sources(test_db, "run-candidate", "hosted-release")["rebound"]
        == []
    )
    test_db.commit()
    assert _record(test_db) == before


def test_pending_dispatch_evidence_prevents_rebinding_without_telemetry(
    test_db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yoke_contracts.timestamps import utc_now

    release = two_project_release(test_db, tmp_path, monkeypatch)
    record_bound_sources(test_db, "run-candidate")
    stamp = utc_now()
    test_db.execute(
        "INSERT INTO github_workflow_dispatch_intents "
        "(request_id,attempt,actor_id,authorization_scope,payload_checksum,repo,workflow,workflow_ref,inputs,correlation_id,state,created_at,updated_at) "
        "VALUES (%s,1,'2','project','checksum','owner/repo','release.yml','main','{}','pending-token','pending',%s,%s)",
        ("deploy:yoke:run-candidate:hosted-release", stamp, stamp),
    )
    test_db.commit()
    before = _record(test_db)
    _move(release)
    with pytest.raises(ValueError, match="create a new run"):
        prepare_bound_sources(test_db, "run-candidate", "hosted-release")
    test_db.rollback()
    assert _record(test_db) == before


def test_unreadable_head_keeps_pins_and_members_unchanged(
    test_db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yoke_core.domain import deployment_run_stale_bound_sources as comparison

    two_project_release(test_db, tmp_path, monkeypatch)
    record_bound_sources(test_db, "run-candidate")
    test_db.commit()
    before = _record(test_db)

    def unreadable(*args, **kwargs):
        raise ValueError("source access unavailable; authorize its repository")

    monkeypatch.setattr(comparison, "_resolve_branch_head", unreadable)
    with pytest.raises(ValueError, match="bound_source_unverified"):
        prepare_bound_sources(test_db, "run-candidate", "hosted-release")
    test_db.rollback()
    assert _record(test_db) == before
    assert not test_db.execute(
        "SELECT 1 FROM deployment_run_items WHERE run_id='run-candidate'"
    ).fetchone()
