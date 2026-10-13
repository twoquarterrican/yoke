"""Bind verdicts to their actual plan execution and its captured artifacts."""

from __future__ import annotations

import json
from typing import Any

from yoke_core.domain.db_helpers import query_one, query_rows
from yoke_core.domain.qa_plan_execution_store import result_rows, select_plan_execution
from yoke_core.domain.schema_common import _table_exists


def _execution(conn: Any, requirement: dict[str, Any], run_id: int) -> dict | None:
    """Prefer an exact captured attempt; aggregate obligations use the scoped walk."""
    rows = query_rows(
        conn,
        "SELECT e.id,r.result_json FROM qa_plan_executions e "
        "JOIN qa_plan_execution_results r ON r.execution_id=e.id "
        "WHERE r.requirement_id=%s ORDER BY e.created_at DESC,e.id DESC",
        (int(requirement["id"]),),
    )
    for row in rows:
        result = json.loads(row["result_json"])
        if result.get("qa_run_id") == run_id or result.get("run_id") == run_id:
            return select_plan_execution(conn, str(row["id"]), lock=False)
    if requirement.get("deployment_run_id") and requirement.get("deployment_stage"):
        rows = query_rows(
            conn,
            "SELECT id FROM qa_plan_executions WHERE deployment_run_id=%s "
            "AND deployment_stage=%s AND COALESCE(deployment_member_item_id,0)=%s "
            "AND execution_target_digest=%s "
            "AND state IN ('active','waiting','awaiting_agent_review','completed') "
            "ORDER BY created_at DESC,id DESC LIMIT 1",
            (
                requirement["deployment_run_id"],
                requirement["deployment_stage"],
                requirement.get("deployment_member_item_id") or 0,
                requirement.get("execution_target_digest") or "",
            ),
        )
    elif requirement.get("standalone_execution_id"):
        return select_plan_execution(
            conn, requirement["standalone_execution_id"], lock=False
        )
    elif requirement.get("item_id"):
        rows = query_rows(
            conn,
            "SELECT id FROM qa_plan_executions WHERE item_id=%s "
            "AND state IN ('active','waiting','awaiting_agent_review','completed') "
            "ORDER BY created_at DESC,id DESC LIMIT 1",
            (int(requirement["item_id"]),),
        )
    else:
        return None
    if not rows:
        return None
    execution = select_plan_execution(conn, str(rows[0]["id"]), lock=False)
    if not requirement.get("deployment_run_id") and not any(
        int(case["requirement_id"]) == int(requirement["id"])
        for case in execution["roster"]
    ):
        return None
    return execution


def link_verdict_evidence(conn: Any, run_id: int) -> None:
    """Stamp execution and concrete artifact ids without changing other proof."""
    if not _table_exists(conn, "qa_plan_executions"):
        return
    run = query_one(conn, "SELECT * FROM qa_runs WHERE id=%s", (run_id,))
    if run is None or run["verdict"] is None:
        return
    requirement = query_one(
        conn, "SELECT * FROM qa_requirements WHERE id=%s", (run["qa_requirement_id"],)
    )
    execution = _execution(conn, requirement, run_id)
    if execution is None:
        return
    evidence_runs = {
        int(value)
        for row in result_rows(conn, str(execution["id"]))
        if (value := row["result"].get("qa_run_id") or row["result"].get("run_id"))
    }
    if requirement.get("method_id"):
        evidence_runs.add(run_id)
    artifacts = []
    if evidence_runs:
        places = ",".join("%s" for _ in evidence_runs)
        artifacts = [
            int(row["id"])
            for row in query_rows(
                conn,
                f"SELECT id FROM qa_artifacts WHERE qa_run_id IN ({places}) ORDER BY id",
                tuple(sorted(evidence_runs)),
            )
        ]
    raw = run.get("raw_result")
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        parsed = None
    payload = (
        dict(parsed) if isinstance(parsed, dict) else ({"evidence": raw} if raw else {})
    )
    payload.update(execution_id=str(execution["id"]), evidence_artifact_ids=artifacts)
    conn.execute(
        "UPDATE qa_runs SET raw_result=%s WHERE id=%s",
        (json.dumps(payload, sort_keys=True, separators=(",", ":")), run_id),
    )


def settle_recorded_verdict(conn: Any, run_id: int) -> None:
    """After capture attachments and verdict commit, re-evaluate the active stage."""
    link_verdict_evidence(conn, run_id)
    conn.commit()
    subject = query_one(
        conn,
        "SELECT q.deployment_run_id,q.deployment_stage,q.deployment_member_item_id "
        "FROM qa_runs r JOIN qa_requirements q ON q.id=r.qa_requirement_id "
        "JOIN deployment_runs d ON d.id=q.deployment_run_id "
        "WHERE r.id=%s AND r.verdict IS NOT NULL AND d.status='executing' "
        "AND d.current_stage=q.deployment_stage",
        (run_id,),
    )
    if subject is not None:
        from yoke_core.domain.deployment_qa_stage_settlement import settle_subject

        settle_subject(
            conn,
            run_id=str(subject["deployment_run_id"]),
            stage=str(subject["deployment_stage"]),
            member=subject["deployment_member_item_id"],
        )
