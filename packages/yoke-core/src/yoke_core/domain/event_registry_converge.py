"""Project the code event catalog into ``event_registry`` on every boot.

The catalog in :mod:`yoke_core.domain.event_catalog` decides which names the
registry holds. Converging inserts a missing name, rewrites a row whose
metadata drifted from its catalog row, and deletes a row the catalog no longer
lists, so every universe serves the vocabulary of the build running it. Rows
already matching their catalog row are not written, so a second run is a
no-op.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from yoke_core.domain.event_catalog import EVENT_CATALOG, EventSpec


@dataclass(frozen=True)
class RegistryConvergence:
    """What one converge pass wrote."""

    written: tuple[str, ...]
    deleted: tuple[str, ...]


_METADATA_SQL = (
    "SELECT event_name, event_kind, event_type, owner_service, "
    "severity_default, description FROM event_registry"
)

_UPSERT_SQL = (
    "INSERT INTO event_registry "
    "(event_name, event_kind, event_type, owner_service, severity_default, "
    "description) VALUES (%s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (event_name) DO UPDATE SET "
    "event_kind = EXCLUDED.event_kind, event_type = EXCLUDED.event_type, "
    "owner_service = EXCLUDED.owner_service, "
    "severity_default = EXCLUDED.severity_default, "
    "description = EXCLUDED.description"
)


def converge_event_registry(conn: Any) -> RegistryConvergence:
    """Make ``event_registry`` hold exactly the catalog; the caller commits."""
    current = {
        row[0]: EventSpec(*row) for row in conn.execute(_METADATA_SQL).fetchall()
    }
    written = tuple(
        name
        for name, spec in sorted(EVENT_CATALOG.items())
        if current.get(name) != spec
    )
    for name in written:
        conn.execute(_UPSERT_SQL, tuple(EVENT_CATALOG[name]))
    deleted = tuple(sorted(set(current) - set(EVENT_CATALOG)))
    if deleted:
        conn.execute(
            "DELETE FROM event_registry WHERE event_name = ANY(%s)", (list(deleted),)
        )
    return RegistryConvergence(written=written, deleted=deleted)


__all__ = ["RegistryConvergence", "converge_event_registry"]
