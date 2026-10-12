"""Drive copied release declarations through receipt allocation, without dispatch.

Only the release control plane records and drives releases, so the replay runs
only on the database holding the run being released (see
:mod:`runtime.api.tools.fleet_rehearsal_release_run`). Every other database is
rehearsed without it and records the check as not applicable because it is not
the release control plane.

Stored runs supply real flows, source revisions and member snapshots. Each
release target (a project environment, or a preview flow) replays its newest
member-bearing run: that lineage is the frontier the next real release composes
against, while an older flow's run on the same environment is superseded and
any real release binding it would be refused as diverged too. The recorded
source revision passed its CI gate when its run was created, so the replay
writes the run without re-asking GitHub: a live provider read proves nothing
about migrated rows and the rehearsal host holds no provider credentials.
Driver attachments and target occupancy are cleared only on the disposable
copy. Every refusal fails proof rather than silently skipping the remaining
path, and a control plane holding no member-bearing release refuses.
"""

from __future__ import annotations

from typing import Any

from yoke_core.domain import db_backend
from yoke_core.domain.deploy_qa_recorder import cmd_seed_from_flow
from yoke_core.domain.deployment_run_create_write import create_run
from yoke_core.domain.handlers import deployment_run_execution as execution
from yoke_core.domain.handlers import deployment_run_execution_receipt as receipts
from yoke_core.domain.migration_fleet_preflight import NotApplicable
from yoke_core.domain.project_checkout_locations import checkout_for_project_id
from yoke_core.domain.project_identity import resolve_project_id
from runtime.api.tools.fleet_rehearsal_release_run import ReleaseRun
from runtime.api.tools.migration_rehearsal_readers import checked


PREBOOT_RELEASE_DRIVER = "preboot_release_driver"


def verify_preboot_release_driver(
    conn: Any, copy_dsn: str, release_run: ReleaseRun | None
) -> str | NotApplicable | None:
    """Replay the release driver on the release control plane's database only."""
    if release_run is None:
        return NotApplicable(
            PREBOOT_RELEASE_DRIVER,
            "no release run named (--release-run), so no database is "
            "identified as the release control plane",
        )
    holds_run = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM deployment_runs "
        "WHERE id=%s AND created_at::timestamptz=%s::timestamptz)",
        (release_run.run_id, release_run.created_at),
    ).fetchone()[0]
    conn.rollback()
    if not holds_run:
        return NotApplicable(
            PREBOOT_RELEASE_DRIVER,
            f"not the release control plane: release run {release_run.run_id} "
            f"is recorded on the {release_run.control_plane} control plane, "
            "not in this database",
        )
    return _replay_release_driver(conn, copy_dsn)


def _replay_release_driver(conn: Any, copy_dsn: str) -> str | None:
    """Run candidate driver code against restored pre-migration rows."""
    operation = "release driver roster"
    try:
        runs = conn.execute(
            "SELECT DISTINCT ON (dr.project_id,dr.target_environment_id,"
            "CASE WHEN dr.target_environment_id IS NULL THEN dr.flow END) "
            "dr.id,p.slug,dr.flow,dr.release_lineage,e.name "
            "FROM deployment_runs dr JOIN deployment_flows df ON df.id=dr.flow "
            "JOIN projects p ON p.id=dr.project_id "
            "LEFT JOIN environments e ON e.id=dr.target_environment_id "
            "WHERE df.status='active' AND dr.release_lineage IS NOT NULL "
            "AND EXISTS (SELECT 1 FROM deployment_run_items m WHERE m.run_id=dr.id) "
            "ORDER BY dr.project_id,dr.target_environment_id,"
            "CASE WHEN dr.target_environment_id IS NULL THEN dr.flow END,"
            "dr.created_at DESC,dr.id DESC"
        ).fetchall()
        if not runs:
            conn.rollback()
            return (
                "preboot_release_subject_missing: this release control plane "
                "stores no member-bearing release to replay; supply a real "
                "release declaration before earning migration rehearsal proof"
            )
        conn.execute("UPDATE deployment_runs SET driver_attachment=NULL")
        conn.execute(
            "UPDATE deployment_runs SET status='cancelled' WHERE status='executing'"
        )
        conn.commit()
        with db_backend.bound_pg_dsn(copy_dsn):
            for predecessor, project, flow, lineage, environment in runs:
                operation = f"run create flow={flow} predecessor={predecessor}"
                run_id = create_run(
                    project,
                    flow,
                    environment=environment,
                    release_lineage=lineage,
                    created_by="migration-rehearsal",
                    inherit_members_from=predecessor,
                ).run_id
                target = {"kind": "workflow_run", "workflow_run_id": run_id}
                operation = f"execution context run={run_id}"
                context = checked(
                    "deployment_runs.execution.context",
                    execution.handle_deployment_execution_context,
                    target=target,
                )
                if not context["members"]:
                    raise RuntimeError(
                        "preboot_member_missing: copied run has no real member"
                    )
                from yoke_core.domain.deployment_run_contained_items import (
                    attest_candidate_containment,
                )

                operation = f"candidate containment run={run_id}"
                attestation = attest_candidate_containment(
                    context["candidate_containment_basis"],
                    lambda slug: str(
                        checkout_for_project_id(resolve_project_id(conn, slug)) or ""
                    ),
                )
                conn.rollback()
                operation = f"QA seed run={run_id}"
                cmd_seed_from_flow(run_id)
                operation = f"start run={run_id}"
                checked(
                    "deployment_runs.execution.update",
                    execution.handle_deployment_execution_update,
                    {
                        "field": "status",
                        "value": "executing",
                        "candidate_containment": attestation,
                    },
                    target,
                )
                stages = [
                    s
                    for s in context["stages"]
                    if s.get("stage_kind", "execution") == "execution"
                ]
                if not stages:
                    raise RuntimeError(
                        "preboot_execution_stage_missing: flow has no execution stage"
                    )
                for stage in stages:
                    operation = f"stage entry run={run_id} stage={stage['name']}"
                    checked(
                        "deployment_runs.execution.update",
                        execution.handle_deployment_execution_update,
                        {"field": "current_stage", "value": stage["name"]},
                        target,
                    )
                    operation = f"receipt allocate run={run_id} stage={stage['name']}"
                    checked(
                        "deployment_runs.execution.stage_receipt_allocate",
                        receipts.handle_deployment_execution_stage_receipt_allocate,
                        {
                            "stage_name": stage["name"],
                            "correlation_id": "migration-rehearsal",
                            "target_kind": "persistent_environment"
                            if environment
                            else "run_preview",
                            "executor": stage.get("step_runner", "auto"),
                        },
                        target,
                    )
                operation = f"copy target release run={run_id}"
                checked(
                    "deployment_runs.execution.update",
                    execution.handle_deployment_execution_update,
                    {"field": "status", "value": "cancelled"},
                    target,
                )
                print(
                    f"PRE_BOOT: {flow}/{environment or 'preview'} member, context, containment, QA seed, start, stage and receipt passed; dispatch not invoked",
                    flush=True,
                )
    except BaseException as exc:  # noqa: BLE001 -- copy verdict
        from yoke_core.domain.migration_fleet_declared_plan import redact_dsn

        return redact_dsn(f"{operation}: {type(exc).__name__}: {exc}", copy_dsn)
    return None
