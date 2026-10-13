"""Retire an unsuccessful deployment's QA on its closing transaction."""

from typing import Any

from yoke_core.domain.db_helpers import query_rows
from yoke_core.domain.qa_latest_execution import latest_execution_id_sql
from yoke_core.domain.qa_obligation_settlement import settled_obligation_sql
from yoke_core.domain.qa_plan_attachment_retract import retract_requirements
from yoke_core.domain.qa_plan_execution_lifecycle import finish_plan_execution
from yoke_core.domain.qa_plan_execution_schema import LIVE_PLAN_EXECUTION_SQL
from yoke_core.domain.qa_plan_execution_store import lock_plan_execution


def settle_unsuccessful_run(conn: Any, run_id: str, *, reason: str) -> None:
    """Abort live cursors and retract unfulfilled run obligations without committing."""
    executions = [
        lock_plan_execution(conn, str(row["id"]))
        for row in query_rows(
            conn,
            "SELECT id FROM qa_plan_executions WHERE deployment_run_id=%s "
            f"AND state IN ({LIVE_PLAN_EXECUTION_SQL}) ORDER BY id",
            (run_id,),
        )
    ]
    # Clear queue intents together before a released host can grant the next
    # cursor from this same closed run.
    for execution in executions:
        conn.execute(
            "UPDATE qa_plan_executions SET release_reason=NULL WHERE id=%s",
            (execution["id"],),
        )
    for execution in executions:
        finish_plan_execution(
            conn, execution, state="aborted", reason=reason, commit=False
        )
    rows = query_rows(
        conn,
        "SELECT r.id FROM qa_requirements r WHERE r.deployment_run_id=%s "
        f"AND NOT {settled_obligation_sql(conn, 'r')} "
        "AND NOT EXISTS (SELECT 1 FROM qa_runs qr "
        f"WHERE qr.id=({latest_execution_id_sql('r.id')}) AND qr.verdict='pass')",
        (run_id,),
    )
    retract_requirements(
        conn, [int(row["id"]) for row in rows], reason=reason, source="operator"
    )
