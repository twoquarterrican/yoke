"""Candidate writes and their repeated reads on the pre-boot TEXT schema."""

import json
from types import SimpleNamespace

import pytest

from runtime.api.domain.test_deployment_composition_clock_filters import (
    DRIVER_STAMP,
    clocks as clocks,
    history,
)
from yoke_contracts.timestamps import InvalidInstant, format_instant, parse_instant
from yoke_core.domain import db_helpers, deploy_qa_recorder, deployment_runs_crud_query
from yoke_core.domain import deployment_run_composition_freeze as composition
from yoke_core.domain import deployment_run_driver_attachment as driver
from yoke_core.domain import merge_queue_landing_marker as marker
from yoke_core.domain import merge_queue_landing_record as records
from yoke_core.domain import merge_queue_landing_refresh as refresh
from yoke_core.domain import preboot_instant_parameters as storage
from yoke_core.domain import deployment_runs_crud_mutate as updates
from yoke_core.domain.qa_latest_execution import select_latest_executions
from yoke_core.domain.qa_run_verdict_record import _clock_columns
from yoke_core.domain.deployment_stage_receipts import (
    DEPLOYMENT_STAGE_RECEIPTS_SQL,
    allocate_deployment_stage_receipt,
    complete_deployment_stage_receipt,
    deployment_stage_receipt_for_qa,
)

RUN = "run-clock-filter"


@pytest.fixture
def preboot(clocks, monkeypatch):
    clocks.execute(
        "ALTER TABLE items ADD merge_queue_pr_number text, ADD merge_queue_enqueued_at text, ADD merge_queue_notified_at text"
    )
    clocks.execute(
        "ALTER TABLE deployment_flows ADD takes_delivery_custody boolean DEFAULT true, ADD stages text DEFAULT '[]'"
    )
    clocks.execute(
        "ALTER TABLE deployment_runs ADD driver_attachment text, ADD composition_frozen_at text, ADD requirement_snapshot text, ADD current_stage text, ADD current_stage_entered_at text, ADD started_at text, ADD completed_at text, ADD carried_work text, ADD bound_sources text, ADD artifact_identity text, ADD composition_resolution text"
    )
    clocks.execute(
        "CREATE TABLE deployment_run_items (run_id text,item_id integer,delivery_intent text,requirement_selection text,requirement_snapshot text)"
    )
    clocks.execute(
        "CREATE TABLE qa_requirements (id integer,item_id integer,qa_kind text,deployment_run_id text,method_id integer,waived_at text,execution_target_digest text,plan_case_key text,"
        "superseded_by_requirement_id integer,replacement_requirement_id integer,retracted_at text,retraction_rationale text,retraction_source text,"
        "waiver_rationale text,waiver_source text,superseded_at text,supersession_rationale text,supersession_source text)"
    )
    clocks.execute(
        "CREATE TABLE qa_runs (id integer,qa_requirement_id integer,started_at text,completed_at text,created_at text,verdict text,case_outcome text,raw_result text)"
    )
    clocks.execute(
        "CREATE TABLE qa_plan_review_verdicts (capture_run_id integer,review_run_id integer,requirement_id integer)"
    )
    clocks.execute(
        "CREATE TABLE item_status_transitions (item_id integer,task_num integer,to_status text,created_at text)"
    )
    clocks.execute(
        "CREATE TABLE merge_queue_landing_refreshes (project_id integer PRIMARY KEY,started_at text,completed_at text,last_error text)"
    )
    clocks.execute(
        "CREATE TABLE merge_queue_landing_records (item_id integer PRIMARY KEY,project_id integer,pr_number text,state text,head_sha text,queue_holding text,queue_entry_state text,merge_when_ready text,failed_checks text,narrative text,disarm_note text,observed_at text,changed_at text)"
    )
    clocks.execute(
        "CREATE TABLE item_sections (item_id integer NOT NULL,section_name text NOT NULL,"
        "content text,ordering integer,source text NOT NULL DEFAULT 'operator',"
        "created_at timestamptz NOT NULL,updated_at timestamptz NOT NULL,"
        "PRIMARY KEY(item_id,section_name))"
    )
    clocks.execute(DEPLOYMENT_STAGE_RECEIPTS_SQL.replace("TIMESTAMPTZ", "TEXT"))
    proxy = SimpleNamespace(
        execute=clocks.execute,
        commit=clocks.commit,
        rollback=clocks.rollback,
        close=lambda: None,
        info=clocks.info,
    )
    monkeypatch.setattr(deployment_runs_crud_query, "connect", lambda *_: proxy)
    monkeypatch.setattr(deploy_qa_recorder, "connect", lambda *_: proxy)
    monkeypatch.setattr(updates, "connect", lambda *_: proxy)
    storage.clear_storage_types()
    yield clocks
    storage.clear_storage_types()


@pytest.mark.parametrize("field", sorted(storage.FIELDS))
def test_declared_writer_is_canonical_on_text_and_native_after_boot(preboot, field):
    table, column = field
    value = db_helpers.instant_parameter(
        preboot, DRIVER_STAMP, table=table, column=column
    )
    assert value == format_instant(DRIVER_STAMP)
    assert parse_instant(value) == DRIVER_STAMP
    history.apply(preboot)
    history.invariants(preboot)
    storage.clear_storage_types()  # The boot owner invalidates after convergence.
    assert (
        db_helpers.instant_parameter(preboot, DRIVER_STAMP, table=table, column=column)
        == DRIVER_STAMP
    )


def test_catalog_is_read_once_per_database_across_connections(preboot):
    reads = []

    def execute(sql, params=()):
        reads.append(sql)
        return preboot.execute(sql, params)

    first = SimpleNamespace(info=preboot.info, execute=execute)
    second = SimpleNamespace(info=preboot.info, execute=execute)
    for conn in (first, second):
        for table, column in storage.FIELDS:
            db_helpers.instant_parameter(conn, DRIVER_STAMP, table=table, column=column)
    assert len(reads) == 1
    with pytest.raises(ValueError, match="undeclared"):
        db_helpers.instant_parameter(
            first, DRIVER_STAMP, table="deployment_runs", column="created_at"
        )
    with pytest.raises(InvalidInstant):
        db_helpers.instant_parameter(
            first, "2026-10-10 23:07:54+00", table="items", column="merged_at"
        )


def test_superseded_marker_skips_old_clocks_then_same_pr_replays_strictly(preboot):
    preboot.execute(
        "UPDATE items SET merge_queue_pr_number='old', merge_queue_enqueued_at='2026-03-09 02:32:26', merge_queue_landed_at='2026-07-30 15:00:27.569899+00', merge_queue_notified_at='2026-07-30 15:00:27+00' WHERE id=1"
    )
    with pytest.raises(InvalidInstant):
        marker.read_landing_marker(preboot, 1)
    assert marker.point_item_at_pull_request(preboot, 1, "new")["landed_at"] is None
    marker.point_item_at_pull_request(preboot, 1, "new", enqueued_at=DRIVER_STAMP)
    assert marker.read_landing_marker(preboot, 1)["enqueued_at"] == DRIVER_STAMP
    assert (
        marker.point_item_at_pull_request(preboot, 1, "new")["enqueued_at"]
        == DRIVER_STAMP
    )


def test_driver_attach_heartbeat_release_keep_canonical_json_on_text(preboot):
    args = dict(
        session_id="driver", pid=42, phase=driver.PHASE_EXECUTING, now=DRIVER_STAMP
    )
    driver.attach_driver(preboot, RUN, **args)
    repeated = driver.attach_driver(preboot, RUN, **args)
    assert repeated.attached_at == DRIVER_STAMP
    assert (
        driver.live_attachment_for_run(preboot, run_id_value=RUN, now=DRIVER_STAMP)
        == repeated
    )
    raw = preboot.execute(
        "SELECT driver_attachment FROM deployment_runs WHERE id=%s", (RUN,)
    ).fetchone()[0]
    assert json.loads(raw)["heartbeat_at"] == format_instant(DRIVER_STAMP)
    assert driver.release_driver(preboot, RUN, session_id="driver", pid=42)


def test_freeze_replay_reads_its_own_canonical_text_stamp(preboot, monkeypatch):
    from yoke_core.domain import deployment_run_unheld_candidates as custody
    from yoke_core.domain import deployment_run_carried_membership_refusal as membership
    from yoke_core.domain import deployment_member_run_coverage as coverage

    monkeypatch.setattr(composition, "record_bound_sources", lambda *_: {})
    monkeypatch.setattr(composition, "record_carried_work", lambda *_: {})
    monkeypatch.setattr(custody, "resolve_candidate_custody", lambda *_: None)
    monkeypatch.setattr(membership, "carried_membership_refusal", lambda *_, **__: None)
    monkeypatch.setattr(
        coverage, "unclosable_final_member_refusal", lambda *_, **__: None
    )
    monkeypatch.setattr(composition, "utc_now", lambda: DRIVER_STAMP)
    preboot.execute(
        "UPDATE deployment_runs SET composition_frozen_at='' WHERE id=%s", (RUN,)
    )
    first = composition.freeze_run_composition(preboot, RUN)
    assert first == composition.freeze_run_composition(preboot, RUN)
    assert first["frozen_at"] == format_instant(DRIVER_STAMP)
    assert deploy_qa_recorder.cmd_seed_from_flow(RUN) == 0


def test_queue_observation_and_refresh_read_their_own_text_clocks(preboot):
    record = records.LandingRecord(
        item_id=1,
        project_id=1,
        pr_number="42",
        state="pending",
        head_sha="a" * 40,
        queue_holding="neither",
        queue_entry_state="absent",
        merge_when_ready="cleared",
        observed_at=DRIVER_STAMP,
        changed_at=DRIVER_STAMP,
    )
    records.write_landing_record(preboot, record)
    assert records.read_landing_record(preboot, 1).observed_at == DRIVER_STAMP
    assert (
        refresh.record_age_seconds(
            records.read_landing_record(preboot, 1).observed_at, now=DRIVER_STAMP
        )
        == 0
    )
    assert refresh.claim_due_projects(preboot, [1], now=DRIVER_STAMP) == (1,)
    refresh.complete_projects(preboot, [1], now=DRIVER_STAMP)
    assert refresh.read_refresh(preboot, 1).completed_at == DRIVER_STAMP
    preboot.execute(
        "UPDATE merge_queue_landing_refreshes SET completed_at='' WHERE project_id=1"
    )
    assert refresh.read_refresh(preboot, 1).completed_at is None
    refresh.fail_projects(preboot, [1], now=DRIVER_STAMP, error="fixture")
    assert refresh.read_refresh(preboot, 1).started_at == DRIVER_STAMP


def test_qa_attempt_order_uses_its_own_canonical_text_start(preboot):
    values = _clock_columns(
        preboot,
        dict(
            started_at=DRIVER_STAMP, completed_at=DRIVER_STAMP, created_at=DRIVER_STAMP
        ),
    )
    preboot.execute(
        "INSERT INTO qa_runs(id,qa_requirement_id,started_at,completed_at,created_at) VALUES (1,2,%s,%s,%s)",
        tuple(values.values()),
    )
    row = dict(preboot.execute("SELECT * FROM qa_runs").fetchone())
    assert select_latest_executions([row])[2]["id"] == 1
    assert all(parse_instant(row[name]) == DRIVER_STAMP for name in values)


def test_receipt_attempts_and_retry_reads_do_not_decode_text_clocks(preboot):
    preboot.execute(
        "UPDATE deployment_flows SET stages=%s WHERE id='successor'",
        (
            json.dumps(
                [dict(name="deploy", stage_kind="execution", step_runner="auto")]
            ),
        ),
    )
    preboot.execute(
        "UPDATE deployment_runs SET status='executing',current_stage='deploy' WHERE id=%s",
        (RUN,),
    )
    params = dict(
        run_id=RUN,
        stage_name="deploy",
        correlation_id="attempt",
        target_kind="persistent_environment",
        executor="fixture",
    )
    receipt = allocate_deployment_stage_receipt(preboot, **params)
    assert allocate_deployment_stage_receipt(preboot, **params)["id"] == receipt["id"]
    completed = complete_deployment_stage_receipt(
        preboot,
        run_id=RUN,
        receipt_id=receipt["id"],
        correlation_id="attempt",
        status="ready",
        target_name="prod",
        observed_release_lineage="a" * 40,
    )
    assert isinstance(completed["completed_at"], str)
    assert (
        deployment_stage_receipt_for_qa(
            preboot,
            run_id=RUN,
            source_stage="deploy",
            expected_target_kind="persistent_environment",
            expected_target_name="prod",
            expected_release_lineage="a" * 40,
        )["id"]
        == receipt["id"]
    )
    for field, expected in (
        ("status", "executing"),
        ("release_lineage", "a" * 40),
        ("flow", "successor"),
    ):
        assert deployment_runs_crud_query.cmd_get(RUN, field) == expected


def test_run_updates_and_retry_projection_leave_unused_clocks_opaque(preboot):
    preboot.execute("UPDATE deployment_runs SET carried_work='{}' WHERE id=%s", (RUN,))
    assert updates.cmd_update(RUN, "current_stage", "deploy") is None
    entered = preboot.execute(
        "SELECT current_stage_entered_at FROM deployment_runs WHERE id=%s", (RUN,)
    ).fetchone()[0]
    assert isinstance(entered, str)
    assert format_instant(parse_instant(entered)) == entered
    assert updates.cmd_update(RUN, "current_stage", "deploy") is None
    assert (
        preboot.execute(
            "SELECT current_stage_entered_at FROM deployment_runs WHERE id=%s", (RUN,)
        ).fetchone()[0]
        == entered
    )
    history.apply(preboot)
    history.invariants(preboot)
    assert updates.cmd_update(RUN, "current_stage", "qa") is None
    native = preboot.execute(
        "SELECT current_stage_entered_at FROM deployment_runs WHERE id=%s", (RUN,)
    ).fetchone()[0]
    assert parse_instant(native) == native
    assert not isinstance(native, str)
    assert updates.cmd_update(RUN, "status", "failed") is None
    assert deployment_runs_crud_query.cmd_get(RUN, "status") == "failed"
    assert "failed" in deployment_runs_crud_query.cmd_get(RUN)
