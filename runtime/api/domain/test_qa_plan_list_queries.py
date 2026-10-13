"""Plan pages retain outcomes while query counts stay independent of row count."""

from datetime import datetime, timezone

from runtime.api.fixtures.pg_testdb import test_database
from runtime.api.qa_catalog_test_support import create_release_readiness_plan
from runtime.api.tools.read_query_profile import CountedConnection
from yoke_core.domain.qa_plan_list_reads import list_plans


def test_full_catalog_queries_do_not_grow_with_plan_count():
    with test_database() as conn:
        create_release_readiness_plan(conn)
        counted = CountedConnection(conn)
        assert len(list_plans(counted, project="yoke", full=True)) == 1
        before = sum(counted.counts.values())
        now = datetime.now(timezone.utc)
        conn.execute(
            "INSERT INTO qa_plans(project_id,slug,name,created_at,updated_at) "
            "SELECT 1, 'catalog-' || n, 'Catalog ' || n, %s, %s "
            "FROM generate_series(1, 60) AS n",
            (now, now),
        )
        counted.counts.clear()
        rows = list_plans(counted, project="yoke", full=True)
        assert len(rows) == 61
        assert sum(counted.counts.values()) == before
        assert before < 20


def test_default_page_has_summary_rows_and_stable_next_page():
    with test_database() as conn:
        now = datetime.now(timezone.utc)
        conn.execute(
            "INSERT INTO qa_plans(project_id,slug,name,description,created_at,updated_at) "
            "SELECT 1, 'catalog-' || lpad(n::text, 3, '0'), 'Catalog ' || n, "
            "repeat('description', 1000), %s, %s FROM generate_series(1, 60) AS n",
            (now, now),
        )
        first = list_plans(conn, project="yoke")
        second = list_plans(conn, project="yoke", offset=25)
        full = list_plans(conn, project="yoke", full=True)
    assert len(first) == len(second) == 25
    assert len(full) == 60
    assert not {row["id"] for row in first} & {row["id"] for row in second}
    assert "execution_target" not in first[0]
    assert "description" not in first[0]
    assert full[0]["description"] == "description" * 1000
