"""Rejected harness probe replies become evidence on the QA run that owns them.

A baseline probe whose reply parser rejected a harness reply carries a
sanitized ``reply_rejection`` record on its failed probe row. The run that
owns that baseline attempt stores each record as a small JSON artifact and
names the rejection in its verdict reason, so the failure stays diagnosable
after a later probe replaces the host's latest operation receipt.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
from pathlib import Path
from typing import Any

ARTIFACT_TYPE = "probe_reply_rejection"


def reply_rejections(evidence: Any) -> list[dict[str, Any]]:
    """Every distinct rejected-reply probe row anywhere in one run's evidence."""
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            record = value.get("reply_rejection")
            if isinstance(record, dict):
                entry = {
                    "probe": value.get("name"),
                    "reason": value.get("reason"),
                    "reply_rejection": record,
                }
                key = json.dumps(entry, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    found.append(entry)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(evidence)
    return found


def rejection_verdict_reason(rejections: list[dict[str, Any]]) -> str | None:
    """Name each rejected probe's parser branch; the artifact holds the record."""
    reasons = []
    for rejection in rejections:
        record = rejection["reply_rejection"]
        events = ", ".join(str(kind) for kind in record.get("event_types") or [])
        reasons.append(
            f"{rejection['probe']}: reply rejected at "
            f"`{record.get('rejection')}` (harness exit "
            f"{record.get('harness_exit_code')}; events: {events or 'none'}); "
            f"see the {ARTIFACT_TYPE} artifact"
        )
    return " | ".join(reasons) or None


def record_reply_rejections(
    conn: Any,
    *,
    requirement_id: int,
    run_id: int,
    rejections: list[dict[str, Any]],
    metadata: dict[str, Any],
    created_at: datetime,
    before_local_write: Callable[[Path], None] | None = None,
) -> list[int]:
    """Store each rejection as a JSON artifact on the run's transaction."""
    from yoke_core.domain import db_backend
    from yoke_core.domain.db_helpers import instant_parameter
    from yoke_core.domain.qa_artifact_handle import parse_handle, serialize_handle
    from yoke_core.domain.qa_artifact_storage import store_artifact_bytes

    marker = "%s" if db_backend.connection_is_postgres(conn) else "?"
    recorded: list[int] = []
    for index, rejection in enumerate(rejections, start=1):
        handle = store_artifact_bytes(
            conn,
            requirement_id=requirement_id,
            run_id=run_id,
            filename=f"probe-reply-rejection-{index}.json",
            content=json.dumps(rejection, sort_keys=True).encode("utf-8"),
            content_type="application/json",
            before_local_write=before_local_write,
        )
        row = conn.execute(
            "INSERT INTO qa_artifacts("
            "qa_run_id,artifact_type,content_type,artifact_handle,metadata,"
            f"created_at) VALUES({', '.join([marker] * 6)}) RETURNING id",
            (
                run_id,
                ARTIFACT_TYPE,
                "application/json",
                serialize_handle(parse_handle(handle)),
                json.dumps(
                    {**metadata, "probe": rejection["probe"]},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                instant_parameter(conn, created_at),
            ),
        ).fetchone()
        recorded.append(int(row[0]))
    return recorded


__all__ = [
    "ARTIFACT_TYPE",
    "record_reply_rejections",
    "rejection_verdict_reason",
    "reply_rejections",
]
