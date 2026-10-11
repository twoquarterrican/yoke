"""The pre-boot gate must reach start and receipt allocation with real members."""

from runtime.api.fixtures.bound_source_release import (
    CARRIER_FLOW,
    CARRIER_ITEM_ID,
    two_project_release,
)
from runtime.api.tools import migration_rehearsal_preboot as preboot
from yoke_core.domain import db_backend, preboot_instant_parameters
from yoke_core.domain.deployment_runs_crud_mutate import cmd_add_item
from yoke_core.domain.domain_refusal import DomainRefusal
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


def test_plan_checks_driver_before_converging():
    assert (
        rehearsal_plan().pre_converge_validator is preboot.verify_preboot_release_driver
    )


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
        detail = preboot.verify_preboot_release_driver(
            test_db, db_backend.resolve_pg_dsn()
        )
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

    monkeypatch.setattr(preboot, "cmd_create_run", refuse)
    detail = preboot.verify_preboot_release_driver(test_db, db_backend.resolve_pg_dsn())
    assert "run create" in detail and "invalid_instant" in detail
    assert (
        test_db.execute("SELECT count(*) FROM deployment_stage_receipts").fetchone()[0]
        == 0
    )


def test_universe_without_release_history_cannot_earn_driver_proof(test_db):
    detail = preboot.verify_preboot_release_driver(test_db, db_backend.resolve_pg_dsn())
    assert "preboot_release_subject_missing" in detail
    assert "supply a real release declaration" in detail
