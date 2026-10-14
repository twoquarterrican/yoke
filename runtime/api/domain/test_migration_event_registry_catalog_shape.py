"""Ordered migration coverage for the catalog-shaped event registry.

The fixture is a converged universe re-shaped by hand into the older one the
entry converts: the three registry columns the catalog does not own put back
and populated the way the retired populator left them.
"""

from __future__ import annotations

import importlib

from yoke_core.domain.migration_restore_point import RESTORE_POINT_ENV
from yoke_core.domain.migration_serving_version import NEXT_RELEASE, declared_minimum
from yoke_core.domain.schema_common import _column_exists
from yoke_core.domain.schema_init import converge_core_schema

ENTRY_NAME = "0076_event_registry_catalog_shape"


def _entry():
    return importlib.import_module(f"yoke_core.domain.migrations.{ENTRY_NAME}")


def test_entry_requires_the_next_release_serving_floor() -> None:
    assert declared_minimum(_entry()) == NEXT_RELEASE


def test_apply_drops_the_retired_columns_and_keeps_every_row(
    test_db, monkeypatch
) -> None:
    monkeypatch.setenv(RESTORE_POINT_ENV, "event-registry-shape-test-snapshot")
    converge_core_schema(test_db)
    test_db.execute(
        "ALTER TABLE event_registry ADD COLUMN status TEXT NOT NULL DEFAULT 'active', "
        "ADD COLUMN added_in TEXT, ADD COLUMN context_schema TEXT"
    )
    test_db.execute(
        "INSERT INTO event_registry (event_name, event_kind, event_type, "
        "owner_service, description, status, added_in, context_schema) VALUES "
        "('ModeChosen', 'workflow', 'mode', 'cli', 'gone', 'retired', 'X-1', '{}')"
    )
    before = test_db.execute("SELECT COUNT(*) FROM event_registry").fetchone()[0]

    _entry().apply(test_db)
    _entry().apply(test_db)
    _entry().invariants(test_db)

    for column in ("status", "added_in", "context_schema"):
        assert not _column_exists(test_db, "event_registry", column), column
    assert (
        test_db.execute("SELECT COUNT(*) FROM event_registry").fetchone()[0] == before
    )
