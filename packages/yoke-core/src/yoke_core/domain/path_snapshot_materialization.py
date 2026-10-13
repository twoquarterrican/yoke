"""Promote a snapshot's planned targets with one write and one event."""

from __future__ import annotations

from yoke_core.domain import db_backend, path_targets_events
from yoke_core.domain.db_helpers import instant_parameter
from yoke_contracts.timestamps import utc_now


def materialize_snapshot_targets(conn, *, target_ids, project_id, commit_sha) -> int:
    ids = sorted({int(value) for value in target_ids})
    if not ids:
        return 0
    p = "%s" if db_backend.connection_is_postgres(conn) else "?"
    rows = conn.execute(
        "UPDATE path_targets SET materialization_state='observed', "
        f"materialization_updated_at={p} WHERE project_id={p} "
        "AND materialization_state IN ('planned','tentative') "
        f"AND id IN ({','.join(p for _ in ids)}) RETURNING id",
        (instant_parameter(conn, utc_now()), project_id, *ids),
    ).fetchall()
    if rows:
        path_targets_events._emit(
            name="PathTargetMaterialized",
            conn=conn,
            project=str(project_id),
            severity="INFO",
            outcome="completed",
            item_id=None,
            session_id=None,
            transactional=True,
            context={
                "project_id": project_id,
                "commit_sha": commit_sha,
                "target_count": len(rows),
                "target_ids": sorted(int(row[0]) for row in rows),
                "new_state": "observed",
            },
        )
    return len(rows)
