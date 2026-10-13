"""Select onboarding runs without crossing project boundaries."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from yoke_core.domain.project_onboarding_schema import _p
from yoke_core.domain.project_onboarding_run_records import ProjectOnboardingRunError
from yoke_core.domain.db_backend import connection_is_postgres
from yoke_core.domain.schema_common import _table_exists


def resolve_run(
    conn: Any,
    *,
    run_id: str | None,
    project_id: int | None,
    lock: bool = False,
) -> tuple[str, Any | None]:
    """Resolve an explicit run or this project's most recent saved run."""
    p = _p(conn)
    lock_sql = " FOR UPDATE" if lock and connection_is_postgres(conn) else ""
    if project_id is not None and project_id <= 0:
        raise ProjectOnboardingRunError(
            "onboarding_project_invalid: use a positive project id."
        )
    if run_id is not None:
        selected = run_id.strip()
        if not selected:
            raise ProjectOnboardingRunError(
                "onboarding_run_invalid: supply a nonblank --run-id."
            )
        existing = conn.execute(
            f"SELECT * FROM project_onboarding_runs WHERE run_id = {p}{lock_sql}",
            (selected,),
        ).fetchone()
        if existing is not None and project_id is not None:
            if existing["project_id"] != project_id:
                raise ProjectOnboardingRunError(
                    "onboarding_project_mismatch: the run belongs to a different "
                    f"project; run yoke onboard checklist --project-id {project_id} "
                    "without --run-id to resume the selected project."
                )
        return selected, existing
    if project_id is not None:
        if lock_sql and _table_exists(conn, "projects"):
            conn.execute(
                f"SELECT id FROM projects WHERE id = {p} FOR UPDATE", (project_id,)
            ).fetchone()
        existing = conn.execute(
            f"SELECT * FROM project_onboarding_runs WHERE project_id = {p} "
            f"ORDER BY updated_at DESC, run_id DESC LIMIT 1{lock_sql}",
            (project_id,),
        ).fetchone()
        if existing is not None:
            return str(existing["run_id"]), existing
    return f"run-{uuid4().hex[:12]}", None
