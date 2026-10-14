"""Production initialization and baseline rows for disposable test universes."""

from yoke_core.domain import db_backend
from yoke_core.domain.environment_bootstrap import run_init_chain
from yoke_core.domain.project_seed_test_helpers import seed_project_identities


def initialize_test_schema(conn):
    """Run the production chain on this connection's database, then seed tests.

    Initialization opens its own connections. Binding the supplied connection's
    name through the captured test-cluster DSN preserves authentication and
    prevents an ambient override from selecting another universe.
    The schema, triggers and constraints retain their production definitions.
    """
    from runtime.api.fixtures import pg_testdb

    pg_testdb._assert_test_db(conn.info.dbname)
    with db_backend.bound_pg_dsn(pg_testdb.dsn_for_test_database(conn.info.dbname)):
        run_init_chain(emit=lambda _line: None)
    seed_project_identities(conn)
    for project_id, name in ((1, "Yoke API"), (2, "External webapp API")):
        conn.execute(
            "INSERT INTO sites(project_id,name,created_at) VALUES(%s,%s,%s) "
            "ON CONFLICT(project_id,name) DO NOTHING",
            (project_id, name, "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO environments(site,project_id,name,created_at) "
            "SELECT id,%s,'development',%s FROM sites "
            "WHERE project_id=%s AND name=%s "
            "ON CONFLICT(project_id,name) DO NOTHING",
            (project_id, "2026-01-01T00:00:00Z", project_id, name),
        )
    conn.commit()
