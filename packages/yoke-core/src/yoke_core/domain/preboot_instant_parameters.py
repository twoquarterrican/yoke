"""Temporary serialization for clocks re-read before native schema boot.

Remove this module and its declared writer arguments once ordered history has
converted every live universe's instant columns. Decoders remain strict.
"""

from threading import RLock
from typing import Any

# Only these clocks are consumed again before the release can boot history,
# or share a SQL expression or comparison with their pre-boot stored value.
FIELDS = frozenset(
    (table, column)
    for table, columns in (
        (
            "items",
            (
                "merged_at",
                "merge_queue_enqueued_at",
                "merge_queue_landed_at",
                "merge_queue_notified_at",
            ),
        ),
        ("merge_queue_landing_records", ("observed_at", "changed_at")),
        ("merge_queue_landing_refreshes", ("started_at", "completed_at")),
        ("deployment_runs", ("composition_frozen_at", "current_stage_entered_at")),
        ("qa_runs", ("started_at", "completed_at", "created_at")),
        ("item_status_transitions", ("created_at",)),
    )
    for column in columns
)
_TYPES: dict[tuple, dict[tuple[str, str], str]] = {}
_LOCK = RLock()


def clear_storage_types() -> None:
    """Boot convergence invalidates process-local catalog knowledge."""
    with _LOCK:
        _TYPES.clear()


def text_storage(conn: Any, table: str, column: str) -> bool:
    """Read the declared live types once per database, never per write."""
    field = (table, column)
    if field not in FIELDS:
        raise ValueError(f"preboot_instant_field_undeclared: {table}.{column}")
    info = getattr(conn, "info", None)
    key = (
        (info.host, info.port, info.dbname, info.user)
        if info is not None
        else (id(conn),)
    )
    with _LOCK:
        if key not in _TYPES:
            rows = conn.execute(
                "SELECT table_name,column_name,data_type FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=ANY(%s)",
                (sorted({name for name, _ in FIELDS}),),
            ).fetchall()
            types = {(str(row[0]), str(row[1])): str(row[2]) for row in rows}
            # Bound memory across disposable databases and tenant universes.
            if len(_TYPES) >= 128:
                _TYPES.clear()
            _TYPES[key] = {name: typ for name, typ in types.items() if name in FIELDS}
        typ = _TYPES[key].get(field)
    if typ not in {"text", "timestamp with time zone"}:
        raise ValueError(f"preboot_instant_storage_invalid: {table}.{column}: {typ}")
    return typ == "text"
