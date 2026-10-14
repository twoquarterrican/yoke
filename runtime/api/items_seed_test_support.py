"""Seed ``items`` rows for item read/write tests by internal id.

Production creates go through ``items.create`` with a spec; these tests need
rows at fixed ids, so they insert through the shared fixture writer.
"""

from __future__ import annotations

from typing import Any

from runtime.api.fixtures.backlog_inserts import insert_item as _insert_fixture_item
from runtime.api.fixtures.file_test_db import connect_test_db


def seed_item(*, item_id: int, workflow: str, db_path: str, **columns: Any) -> None:
    """Insert one item row at ``item_id`` pinned to ``workflow``."""
    conn = connect_test_db(db_path)
    try:
        _insert_fixture_item(conn, id=item_id, workflow_id=workflow, **columns)
        conn.commit()
    finally:
        conn.close()
