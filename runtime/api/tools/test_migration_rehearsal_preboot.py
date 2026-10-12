"""The pre-boot gate must reach start and receipt allocation with real members.

Only the release control plane's database, the one holding the run being
released, replays the driver; every other database records it not applicable.
"""

from runtime.api.fixtures.bound_source_release import (
    CARRIER_FLOW,
    CARRIER_ITEM_ID,
    bound_stages,
    two_project_release,
)
from runtime.api.fixtures.carried_release_candidate import insert_run
from yoke_core.domain.flow_create import cmd_create
from runtime.api.tools import migration_rehearsal_preboot as preboot
from yoke_core.domain import (
    db_backend,
    deployment_run_ci_tested_source as ci_tested_source,
    preboot_instant_parameters,
)
from yoke_core.domain.deployment_run_ci_tested_source import (
    UNVERIFIABLE,
    ReleaseSourceRefused,
)
from yoke_core.domain.migration_fleet_preflight import NotApplicable
from yoke_core.domain.deployment_runs_crud_mutate import cmd_add_item
from yoke_core.domain.domain_refusal import DomainRefusal
from runtime.api.tools.fleet_rehearsal_release_run import ReleaseRun
from runtime.api.tools.yoke_migration_fleet import rehearsal_plan


def setup_release(conn, tmp_path, monkeypatch):
    fixture = two_project_release(conn, tmp_path, monkeypatch)
    conn.execute(
        "UPDATE deployment_flows SET status='active',target_tier='persistent',"
        "target_environment_id=(SELECT id FROM environments WHERE project_id=1 AND name='stage') WHERE id=%s",
        (CARRIER_FLOW,),
    )
    conn.execute(
        "UPDATE deployment_runs SET target_tier='persistent',"
        "target_environment_id=(SELECT id FROM environments WHERE project_id=1 AND name='stage') WHERE flow=%s",
        (CARRIER_FLOW,),
    )
    conn.commit()
    cmd_add_item("run-candidate", CARRIER_ITEM_ID)
    conn.execute(
        "UPDATE deployment_runs SET status='succeeded' WHERE id='run-candidate'"
    )
    conn.commit()
    monkeypatch.setattr(
        preboot,
        "checkout_for_project_id",
        lambda pid: (
            fixture["carrier_repo"] if int(pid) == 1 else fixture["consumer_repo"]
        ),
    )
    return fixture


def held_run(conn, run_id="run-candidate"):
    """The run being released, exactly as this database records it."""
    created_at = conn.execute(
        "SELECT created_at FROM deployment_runs WHERE id=%s", (run_id,)
    ).fetchone()[0]
    return ReleaseRun(run_id, created_at.isoformat(), "prod")


def replay(conn, release_run=None):
    return preboot.verify_preboot_release_driver(
        conn, db_backend.resolve_pg_dsn(), release_run or held_run(conn)
    )


def replayed_runs(conn):
    return conn.execute(
        "SELECT count(*) FROM deployment_runs WHERE created_by='migration-rehearsal'"
    ).fetchone()[0]


def test_plan_checks_driver_for_the_named_release_before_converging():
    release_run = ReleaseRun("run-1", "2026-10-12T00:00:00+00:00", "prod")
    validator = rehearsal_plan(release_run).pre_converge_validator
    assert validator.func is preboot.verify_preboot_release_driver
    assert validator.keywords == {"release_run": release_run}


def test_real_member_context_start_and_receipt_on_text_schema(
    test_db, tmp_path, monkeypatch
):
    setup_release(test_db, tmp_path, monkeypatch)
    from yoke_core.domain.merge_queue_landing_record_schema import (
        ensure_merge_queue_landing_record_schema,
    )

    ensure_merge_queue_landing_record_schema(test_db)
    # Reproduce the pre-boot storage types while retaining complete product
    # tables and real release declarations, rather than stub driver logic.
    for table, column in preboot_instant_parameters.FIELDS:
        test_db.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE TEXT USING {column}::text"
        )
    test_db.commit()
    preboot_instant_parameters.clear_storage_types()
    try:
        detail = replay(test_db)
        assert detail is None, detail
        row = test_db.execute(
            "SELECT dr.status,count(m.item_id) FROM deployment_runs dr "
            "JOIN deployment_run_items m ON m.run_id=dr.id "
            "WHERE dr.created_by='migration-rehearsal' GROUP BY dr.id,dr.status"
        ).fetchone()
        assert row[0] == "cancelled" and row[1] > 0
        assert (
            test_db.execute(
                "SELECT count(*) FROM deployment_stage_receipts"
            ).fetchone()[0]
            > 0
        )
    finally:
        preboot_instant_parameters.clear_storage_types()


def test_refused_create_cannot_silently_pass_rest_of_driver(
    test_db, tmp_path, monkeypatch
):
    setup_release(test_db, tmp_path, monkeypatch)

    def refuse(*_, **__):
        raise DomainRefusal("invalid_instant: copied driver failed")

    monkeypatch.setattr(preboot, "create_run", refuse)
    detail = replay(test_db)
    assert "run create" in detail and "invalid_instant" in detail
    assert (
        test_db.execute("SELECT count(*) FROM deployment_stage_receipts").fetchone()[0]
        == 0
    )


def test_replay_never_asks_ci_provider_about_recorded_source(
    test_db, tmp_path, monkeypatch
):
    setup_release(test_db, tmp_path, monkeypatch)

    def no_credentials(*_, **__):
        raise ReleaseSourceRefused(
            UNVERIFIABLE, "missing_app_credentials: GitHub App credentials unavailable"
        )

    monkeypatch.setattr(ci_tested_source, "require_tested_lineage", no_credentials)
    monkeypatch.setattr(ci_tested_source, "bind_tested_release_source", no_credentials)
    detail = replay(test_db)
    assert detail is None, detail


def test_each_target_replays_only_its_newest_release(test_db, tmp_path, monkeypatch):
    setup_release(test_db, tmp_path, monkeypatch)
    cmd_create(test_db, "superseded-flow", "yoke", "Old", "", bound_stages())
    stage = "(SELECT id FROM environments WHERE project_id=1 AND name='stage')"
    test_db.execute(
        "UPDATE deployment_flows SET status='active',target_tier='persistent',"
        f"target_environment_id={stage} "
        "WHERE id='superseded-flow'"
    )
    insert_run(
        test_db,
        "run-superseded",
        lineage="f" * 40,
        status="created",
        flow="superseded-flow",
    )
    test_db.execute(
        "UPDATE deployment_runs SET target_tier='persistent',"
        f"target_environment_id={stage},"
        "created_at='2026-09-01T00:00:00Z' WHERE id='run-superseded'"
    )
    test_db.commit()
    cmd_add_item("run-superseded", CARRIER_ITEM_ID)
    test_db.execute(
        "UPDATE deployment_runs SET status='succeeded' WHERE id='run-superseded'"
    )
    test_db.commit()
    detail = replay(test_db)
    assert detail is None, detail
    flows = test_db.execute(
        "SELECT flow FROM deployment_runs WHERE created_by='migration-rehearsal'"
    ).fetchall()
    assert flows == [(CARRIER_FLOW,)]


def test_tenant_with_member_less_runs_is_not_the_release_control_plane(
    test_db, tmp_path, monkeypatch
):
    setup_release(test_db, tmp_path, monkeypatch)
    test_db.execute("DELETE FROM deployment_run_items")
    test_db.commit()
    elsewhere = ReleaseRun("run-20261012-013", "2026-10-12T23:08:55.380656Z", "prod")
    outcome = replay(test_db, elsewhere)
    assert isinstance(outcome, NotApplicable)
    assert outcome.check == preboot.PREBOOT_RELEASE_DRIVER
    assert outcome.reason.startswith("not the release control plane")
    assert "run-20261012-013" in outcome.reason and "prod" in outcome.reason
    assert replayed_runs(test_db) == 0


def test_same_run_id_from_another_universe_is_not_the_control_plane(
    test_db, tmp_path, monkeypatch
):
    setup_release(test_db, tmp_path, monkeypatch)
    other = ReleaseRun("run-candidate", "2001-01-01T00:00:00+00:00", "prod")
    outcome = replay(test_db, other)
    assert isinstance(outcome, NotApplicable)
    assert "not the release control plane" in outcome.reason
    assert replayed_runs(test_db) == 0


def test_no_named_release_run_identifies_no_control_plane(test_db):
    outcome = preboot.verify_preboot_release_driver(
        test_db, db_backend.resolve_pg_dsn(), None
    )
    assert isinstance(outcome, NotApplicable)
    assert "--release-run" in outcome.reason


def test_control_plane_without_member_bearing_release_cannot_earn_driver_proof(
    test_db, tmp_path, monkeypatch
):
    setup_release(test_db, tmp_path, monkeypatch)
    test_db.execute("DELETE FROM deployment_run_items")
    test_db.commit()
    detail = replay(test_db)
    assert "preboot_release_subject_missing" in detail
    assert "supply a real release declaration" in detail
