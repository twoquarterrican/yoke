"""Prepare and durably consume the exact bound inputs a stage will dispatch."""

from __future__ import annotations
import json
from copy import deepcopy
from typing import Any
from yoke_contracts.timestamps import format_instant, utc_now
from yoke_core.domain.deployment_run_bound_sources import (
    parse_bound_sources,
    declared_bindings,
    bound_sources_recorded,
)
from yoke_core.domain.deployment_run_stale_bound_sources import _compare_to_branch_heads
from yoke_core.domain.deployment_run_project_sources import invalidate_run_source_facts
from yoke_core.domain.deployment_run_bound_source_composition import (
    recompose_bound_sources,
    preview_bound_source_composition,
)
from yoke_core.domain.deployment_runs_lock import lock_run_with_stable_membership
from yoke_core.domain.json_helper import dumps_compact
from yoke_core.domain.deployment_run_bound_source_consumption import consumed_stage
from yoke_core.domain.workflow_item_binding_lock import lock_item_workflow_bindings


def prepare_bound_sources(conn: Any, run_id: str, stage_name: str) -> dict[str, Any]:
    """Refresh unused sources, recompose, then seal this stage's inputs.

    The caller commits before dispatch. A crash after commit conservatively
    keeps the source consumed, protecting any ambiguous provider attempt.
    """
    if not bound_sources_recorded(conn):
        raise ValueError(
            f"bound_source_record_unavailable: {run_id} cannot record consumption; ask the control-plane operator to converge the bound_sources column"
        )
    row = conn.execute(
        "SELECT dr.bound_sources,df.stages,dr.current_stage,dr.status FROM deployment_runs dr JOIN deployment_flows df ON df.id=dr.flow WHERE dr.id=%s",
        (run_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"deployment run {run_id!r} not found")
    stored, stages_text, current_stage, status = row
    if status not in {"created", "executing", "failed"}:
        raise ValueError(
            f"bound_source_run_terminal: {run_id} is {status}; compose a new run"
        )
    snapshot = deepcopy(parse_bound_sources(stored))
    record = deepcopy(snapshot)
    stages = json.loads(str(stages_text or "[]"))
    stage = next((s for s in stages if s.get("name") == stage_name), None)
    if stage is None or not stage.get("input_bindings"):
        raise ValueError(
            f"bound_source_stage_invalid: {stage_name!r} declares no bound inputs; select a bound stage on {run_id}"
        )
    declared = declared_bindings(stages)
    branches = {v["project"]: v["branch"] for v in declared.values()}
    entries = record.get("projects") or []
    needed = {v["project"] for v in declared_bindings([stage]).values()}
    if needed - {e["project"] for e in entries}:
        raise ValueError(
            f"bound_source_record_incomplete: {run_id} is missing {sorted(needed)}; compose a new run"
        )
    selected = [e for e in entries if e["project"] in needed]
    stale, unverified = _compare_to_branch_heads(conn, run_id, selected, branches)
    if unverified:
        raise ValueError(
            f"bound_source_unverified: {unverified}; repair source access, then re-drive {run_id}"
        )
    changes = {e["project"]: e for e in stale}
    for entry in selected:
        if entry["project"] not in changes:
            continue
        consumed = entry.get("consumed_by") or consumed_stage(
            conn, run_id, entry["project"], stages, str(current_stage or "")
        )
        if consumed or entry.get("outputs") or entry.get("promotion_receipts"):
            raise ValueError(changes[entry["project"]]["reason"])
    stamp = format_instant(utc_now())
    for entry in selected:
        change = changes.get(entry["project"])
        if change:
            entry.setdefault("rebindings", []).append(
                dict(
                    from_sha=entry["commit_sha"],
                    to_sha=change["current_sha"],
                    before_stage=stage_name,
                    recorded_at=stamp,
                )
            )
            entry["commit_sha"] = change["current_sha"]
            for key, binding in declared.items():
                if binding["project"] == entry["project"]:
                    record["inputs"][key] = entry["commit_sha"]
    project_ids = frozenset(
        int(e["project_id"]) for e in selected if e["project"] in changes
    )
    preview = (
        preview_bound_source_composition(conn, run_id, record, project_ids)
        if changes
        else None
    )
    if preview is not None:
        lock_item_workflow_bindings(conn, preview.lock_item_ids)
    locked_status, _ = lock_run_with_stable_membership(conn, run_id)
    latest = conn.execute(
        "SELECT bound_sources FROM deployment_runs WHERE id=%s", (run_id,)
    ).fetchone()[0]
    if locked_status != status or parse_bound_sources(latest) != snapshot:
        raise ValueError(
            f"bound_source_preparation_changed: {run_id} changed during preparation; re-drive the same run"
        )
    if changes:
        conn.execute(
            "UPDATE deployment_runs SET bound_sources=%s WHERE id=%s",
            (dumps_compact(record), run_id),
        )
        invalidate_run_source_facts(conn, run_id)
        recompose_bound_sources(conn, run_id, project_ids, preview)
    for entry in selected:
        entry.setdefault("consumed_by", stage_name)
        entry.setdefault("consumed_at", stamp)
    conn.execute(
        "UPDATE deployment_runs SET bound_sources=%s WHERE id=%s",
        (dumps_compact(record), run_id),
    )
    invalidate_run_source_facts(conn, run_id)
    return {
        "bound_sources": record,
        "rebound": [
            {key: value for key, value in change.items() if key != "reason"}
            for change in stale
        ],
    }
