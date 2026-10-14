"""Boot convergence retains project-owned flows and historical deployments."""

from __future__ import annotations
from pathlib import Path
from runtime.api.fixtures.file_test_db import connect_test_db, init_test_db
from yoke_core.domain.schema_common import _column_exists
from yoke_core.domain.schema_init import converge_core_schema


def test_converge_adds_flow_status_without_inventing_project_definitions(
    tmp_path: Path,
) -> None:
    """A release boot repairs schema but leaves flow ownership to projects."""
    with init_test_db(tmp_path) as db_path:
        conn = connect_test_db(db_path)
        try:
            conn.execute(
                "INSERT INTO deployment_flows "
                "(id, project_id, name, description, stages, on_failure, "
                "created_at) VALUES (%s, "
                "(SELECT id FROM projects ORDER BY id LIMIT 1), "
                "%s, %s, %s, %s, %s)",
                (
                    "project-owned-flow",
                    "Project owned",
                    "Repository declaration",
                    "[]",
                    "halt",
                    "2026-07-19T00:00:00Z",
                ),
            )
            conn.execute(
                "DELETE FROM deployment_flows WHERE id=%s",
                ("project-owned-flow",),
            )
            conn.execute("ALTER TABLE deployment_flows DROP COLUMN status")
            conn.commit()

            converge_core_schema(conn)

            assert _column_exists(conn, "deployment_flows", "status") is True
            row = conn.execute(
                "SELECT id FROM deployment_flows WHERE id=%s",
                ("project-owned-flow",),
            ).fetchone()
            assert row is None
        finally:
            conn.close()


def test_converge_preserves_disabled_flow_and_historical_run(
    tmp_path: Path,
) -> None:
    """Catalog convergence never re-enables definitions or purges run history."""
    with init_test_db(tmp_path) as db_path:
        conn = connect_test_db(db_path)
        try:
            converge_core_schema(conn)
            conn.execute(
                "INSERT INTO deployment_flows "
                "(id, project_id, name, description, stages, on_failure, "
                "status, created_at) VALUES (%s, "
                "(SELECT id FROM projects ORDER BY id LIMIT 1), "
                "%s, %s, %s, %s, %s, %s)",
                (
                    "project-owned-flow",
                    "Project owned",
                    "Repository declaration",
                    "[]",
                    "halt",
                    "disabled",
                    "2026-07-19T00:00:00Z",
                ),
            )
            conn.execute("DROP TABLE deployment_run_qa CASCADE")
            conn.execute("DROP TABLE deployment_run_items CASCADE")
            conn.execute("DROP TABLE deployment_runs CASCADE")
            conn.execute(
                "CREATE TABLE deployment_runs ("
                "id TEXT PRIMARY KEY, "
                "project_id INTEGER NOT NULL REFERENCES projects(id), "
                "flow TEXT NOT NULL REFERENCES deployment_flows(id), "
                "target_env TEXT, status TEXT, current_stage TEXT)"
            )
            conn.execute(
                "CREATE TABLE deployment_run_items ("
                "run_id TEXT REFERENCES deployment_runs(id), item_id INTEGER)"
            )
            conn.execute(
                "CREATE TABLE deployment_run_qa ("
                "run_id TEXT REFERENCES deployment_runs(id), "
                "check_name TEXT, status TEXT, updated_at TEXT)"
            )
            conn.execute(
                "INSERT INTO deployment_runs "
                "(id, project_id, flow, status, current_stage) "
                "VALUES (%s, (SELECT id FROM projects WHERE slug = %s), "
                "%s, %s, %s)",
                (
                    "run-20260716-999",
                    "yoke",
                    "project-owned-flow",
                    "succeeded",
                    "complete",
                ),
            )
            conn.commit()

            converge_core_schema(conn)

            status = conn.execute(
                "SELECT status FROM deployment_flows WHERE id = 'project-owned-flow'"
            ).fetchone()[0]
            run_count = conn.execute(
                "SELECT COUNT(*) FROM deployment_runs WHERE id = 'run-20260716-999'"
            ).fetchone()[0]
            assert status == "disabled"
            assert int(run_count) == 1
        finally:
            conn.close()
