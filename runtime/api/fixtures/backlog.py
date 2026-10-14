"""Production-schema test_db and insert helpers.

The shared database is a reusable clone of the production initialization
chain. It carries production constraints and triggers. Insert helpers live in
backlog_inserts; operating-actor machine configuration is recorded per test.
"""

from __future__ import annotations

from typing import Any

import pytest

from yoke_core.domain.actors import seed_canonical_human
from yoke_core.domain.sql_json import JSONB_COLUMNS  # noqa: F401 — imported for cross-reference
from runtime.api.fixtures.backlog_inserts import (
    insert_deployment_run,
    insert_epic_task,
    insert_event,
    insert_item,
    insert_item_worktree,
    insert_qa_requirement,
    insert_qa_run,
)
from runtime.api.fixtures.operating_actor import (
    record_fixture_operating_actor,
)


def seed_test_canonical_human(conn: Any) -> int:
    """Seed the universe's local human actor on a fixture DB.

    Mirrors the post-init shape that production
    ``schema_init.cmd_init`` produces, so writer tests that depend on
    actor resolution have the default human actor available without
    every caller re-seeding by hand. Returns the human's actor id
    exactly like the production helper.
    """
    return seed_canonical_human(conn)


def seed_fixture_operating_actor(conn: Any) -> int:
    """Seed the operating actor session registration binds, when absent.

    Every born universe carries one — ``schema_init.cmd_init`` seeds it —
    and registration refuses rather than storing a NULL actor, so a
    fixture without one models an install that cannot exist. Birth also
    records WHICH actor this machine operates the universe as, so this
    records that binding too; without it the seeded actor exists and no
    session can name it. A fixture whose schema also carries the
    org/role tables gets the admin grant a real universe gives its
    operator, because the dispatcher enforces permissions as soon as a
    session names an actor. Idempotent, and a minimal ``actors``-only
    schema still works.
    """
    from yoke_core.domain.actors import seed_human_actor
    from yoke_core.domain.schema_common import _table_exists

    if all(
        _table_exists(conn, table)
        for table in ("actors", "actor_org_roles", "organizations", "roles")
    ):
        from yoke_core.domain.local_operating_actor import (
            ensure_local_operating_actor,
        )

        actor_id, _seeded = ensure_local_operating_actor(conn)
        record_fixture_operating_actor(conn, actor_id)
        return actor_id
    row = conn.execute(
        "SELECT id FROM actors WHERE kind = 'human' ORDER BY id LIMIT 1"
    ).fetchone()
    actor_id = int(row[0]) if row is not None else seed_human_actor(conn)
    record_fixture_operating_actor(conn, actor_id)
    return actor_id


@pytest.fixture
def test_db():
    """Connection with the full Yoke schema on a disposable Postgres DB.

    Seeds the canonical yoke-core + local human actors, and records the
    operating-actor binding beside them, so writer tests resolving the
    default actor see the same post-init shape production ships.
    """
    from runtime.api.fixtures.pg_testdb import test_database

    with test_database() as conn:
        local_human = seed_test_canonical_human(conn)
        conn.commit()
        # A born universe also records which actor this machine operates
        # it as; without that, no session in the fixture can register.
        record_fixture_operating_actor(conn, local_human)
        yield conn


__all__ = (
    "JSONB_COLUMNS",
    "insert_deployment_run",
    "insert_epic_task",
    "insert_event",
    "insert_item",
    "insert_item_worktree",
    "insert_qa_requirement",
    "insert_qa_run",
    "seed_test_canonical_human",
    "test_db",
)
