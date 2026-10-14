"""Native SQL execution for tests of intentionally partial schemas."""

from typing import Any


def apply_fixture_ddl(conn: Any, ddl: str) -> None:
    """Apply inline test DDL one statement at a time and commit it."""
    from yoke_core.domain.schema_init_apply import execute_schema_script

    execute_schema_script(conn, ddl)
    conn.commit()
