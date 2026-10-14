"""Registry reads for the Yoke event platform.

``event_registry`` rows are projected from the code event catalog
(:mod:`yoke_core.domain.event_catalog`) on every boot, so this module only
reads them: ``cmd_registry_get``, ``cmd_registry_list`` and
``cmd_registry_count``.

Discovery primitives (AST/regex helpers + ``cmd_registry_discover``) live
in ``events_registry_discovery``. Reporting queries
(``cmd_registry_audit``, ``cmd_registry_diff``) live in
``events_registry_audit``. This module re-exports those names so the
public surface that ``events_crud`` re-exports stays in one place.

Imports of constants/helpers from ``events_crud`` happen lazily inside
each function. ``events_crud`` does a late re-export from this module
after defining its own helpers; binding ``events_crud`` symbols at
module top-level here would re-enter the partially-initialised
``events_crud`` whenever a caller imports ``events_reporting`` directly,
which raises ``ImportError`` for the late-bound names. Function-local
imports break that cycle while preserving ``events_crud``'s late
re-export.
"""

from __future__ import annotations

from typing import Any, Optional

from yoke_core.domain.db_helpers import connect, query_one, query_rows, query_scalar

# Re-exports: discovery primitives + cmd_registry_discover.
from yoke_core.domain.events_registry_discovery import (
    _discover_python_event_names,
    _extract_event_name_from_line,
    _join_continuation_lines,
    _py_call_name,
    _py_string_value,
    _validate_event_name,
    cmd_registry_discover,
)

# Re-exports: registry audit + diff.
from yoke_core.domain.events_registry_audit import (
    cmd_registry_audit,
    cmd_registry_diff,
)

__all__ = [
    "_discover_python_event_names",
    "_extract_event_name_from_line",
    "_join_continuation_lines",
    "_py_call_name",
    "_py_string_value",
    "_validate_event_name",
    "cmd_registry_audit",
    "cmd_registry_count",
    "cmd_registry_diff",
    "cmd_registry_discover",
    "cmd_registry_get",
    "cmd_registry_list",
]


def cmd_registry_get(db_path: Optional[str] = None, name: str = "") -> str:
    """Get a registry entry. Returns pipe-delimited string or raises."""
    from yoke_core.domain.events_select import _REG_SELECT_COLS

    conn = connect(db_path)
    try:
        row = query_one(
            conn,
            f"SELECT {_REG_SELECT_COLS} FROM event_registry WHERE event_name=%s",
            (name,),
        )
        if row is None:
            raise LookupError(f"event '{name}' not found in registry")
        return "|".join(str(v) for v in tuple(row))
    finally:
        conn.close()


def cmd_registry_list(
    db_path: Optional[str] = None,
    kind: Optional[str] = None,
    service: Optional[str] = None,
) -> str:
    """List registry entries with optional filters."""
    from yoke_core.domain.events_select import _REG_SELECT_COLS, _format_rows

    parts: list[str] = []
    params: list[Any] = []

    if kind:
        parts.append("event_kind=%s")
        params.append(kind)
    if service:
        parts.append("owner_service=%s")
        params.append(service)

    where = ("WHERE " + " AND ".join(parts)) if parts else ""
    conn = connect(db_path)
    try:
        rows = query_rows(
            conn,
            f"SELECT {_REG_SELECT_COLS} FROM event_registry {where} "
            "ORDER BY event_name ASC",
            tuple(params),
        )
        return _format_rows(rows)
    finally:
        conn.close()


def cmd_registry_count(db_path: Optional[str] = None) -> int:
    """Count registry entries."""
    conn = connect(db_path)
    try:
        return query_scalar(conn, "SELECT COUNT(*) FROM event_registry")
    finally:
        conn.close()
