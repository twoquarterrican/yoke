"""Reduce ``event_registry`` to the columns the code event catalog owns.

Every boot now makes the registry rows equal the catalog in
``yoke_core.domain.event_catalog``, so membership itself says a name is
live. ``status`` no longer distinguishes anything: a name with no producer
is deleted rather than marked ``deprecated`` or ``retired``. ``added_in``
held work-item provenance and ``context_schema`` was set only on a name the
catalog no longer lists; the catalog carries neither, so the projection
would leave both empty forever.
"""

from __future__ import annotations

from typing import Any

from yoke_core.domain.migration_serving_version import NEXT_RELEASE
from yoke_core.domain.schema_common import _column_exists, _table_exists


#: A build older than this entry selects ``status`` (and the two dropped
#: metadata columns) on every registry read, so it cannot serve a database
#: this entry has converged.
MINIMUM_SERVING_VERSION = NEXT_RELEASE

TABLE = "event_registry"
RETIRED_COLUMNS = ("status", "added_in", "context_schema")


def apply(conn: Any) -> None:
    """Drop each retired column that is still present."""
    if not _table_exists(conn, TABLE):
        return
    for column in RETIRED_COLUMNS:
        if _column_exists(conn, TABLE, column):
            conn.execute(f'ALTER TABLE "{TABLE}" DROP COLUMN "{column}"')


def invariants(conn: Any) -> None:
    """Prove no retired column remains on the registry."""
    if not _table_exists(conn, TABLE):
        return
    for column in RETIRED_COLUMNS:
        assert not _column_exists(conn, TABLE, column), (
            f"{TABLE}.{column} remains after the catalog-shape convergence"
        )


__all__ = [
    "MINIMUM_SERVING_VERSION",
    "RETIRED_COLUMNS",
    "TABLE",
    "apply",
    "invariants",
]
