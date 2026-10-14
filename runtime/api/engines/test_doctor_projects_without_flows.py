"""Doctor checks project-owned deployment flow coverage and absent schema."""

from yoke_core.engines.doctor import hc_projects_without_flows
from runtime.api.engines._doctor_hc_db_full_test_helpers import _result, _run_hc


_TEST_PROJECT_IDS = {
    "yoke": 1,
    "externalwebapp": 2,
    "proj-a": 10,
    "proj-b": 11,
    "proj-c": 12,
    "proj-d": 13,
    "proj-e": 14,
    "proj-f": 15,
}


def _project_id(slug: str) -> int:
    return _TEST_PROJECT_IDS[slug]


class TestHCProjectsWithoutFlows:
    """Tests for HC-projects-without-flows."""

    def _add_project(self, conn, project_id):
        conn.execute(
            "INSERT INTO projects "
            "(id, slug, name, created_at, public_item_prefix) "
            "VALUES (%s, %s, %s, %s, 'YOK') "
            "ON CONFLICT (id) DO UPDATE SET "
            "slug=EXCLUDED.slug, name=EXCLUDED.name",
            (
                _project_id(project_id),
                project_id,
                project_id,
                "2026-01-01T00:00:00Z",
            ),
        )
        conn.commit()

    def _add_flow(self, conn, flow_id, project_id):
        conn.execute(
            "INSERT INTO deployment_flows "
            "(id, project_id, name, stages, created_at) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (
                flow_id,
                _project_id(project_id),
                f"flow-{flow_id}",
                "[]",
                "2026-01-01T00:00:00Z",
            ),
        )
        conn.commit()

    def _cover_seeded_projects(self, conn):
        self._add_flow(conn, "flow-yoke", "yoke")
        self._add_flow(conn, "flow-externalwebapp", "externalwebapp")

    def test_pass_all_projects_have_flows(self, test_db):
        """Test 1: PASS when all projects have deployment flows."""
        self._cover_seeded_projects(test_db)
        self._add_project(test_db, "proj-a")
        self._add_flow(test_db, "flow-a", "proj-a")
        rec = _run_hc(hc_projects_without_flows, test_db)
        assert _result(rec).result == "PASS"

    def test_warn_project_no_flows(self, test_db):
        """Test 2: WARN when a project has no deployment flows."""
        self._add_project(test_db, "proj-b")
        rec = _run_hc(hc_projects_without_flows, test_db)
        r = _result(rec)
        assert r.result == "WARN"
        assert "proj-b" in r.detail

    def test_warn_multiple_projects_without_flows(self, test_db):
        """Test 3: WARN lists multiple projects without flows."""
        self._add_project(test_db, "proj-c")
        self._add_project(test_db, "proj-d")
        self._add_project(test_db, "proj-e")
        self._add_flow(test_db, "flow-e", "proj-e")
        rec = _run_hc(hc_projects_without_flows, test_db)
        r = _result(rec)
        assert "proj-c" in r.detail
        assert "proj-d" in r.detail
        assert "proj-e" not in r.detail

    def test_graceful_no_deployment_flows_table(self, test_db):
        """Test 4: Graceful when deployment_flows table is missing."""
        self._add_project(test_db, "proj-f")
        test_db.execute("DROP TABLE IF EXISTS deployment_flows CASCADE")
        test_db.commit()
        rec = _run_hc(hc_projects_without_flows, test_db)
        r = _result(rec)
        assert r.result == "WARN"
        assert "deployment_flows table" in r.detail

    def test_graceful_no_projects_table(self, test_db):
        """Test 5: Graceful when projects table is missing."""
        test_db.execute("DROP TABLE IF EXISTS deployment_flows CASCADE")
        test_db.execute("DROP TABLE IF EXISTS projects CASCADE")
        test_db.commit()
        rec = _run_hc(hc_projects_without_flows, test_db)
        assert _result(rec).result == "PASS"
