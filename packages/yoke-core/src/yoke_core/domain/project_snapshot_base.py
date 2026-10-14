"""Incremental snapshot uploads: pick a stored base, then assemble on it.

A client syncing a commit offers the commits it can diff against. The server
answers with the first one whose content snapshot it already holds; the
client then uploads only the files whose blob differs from that base. At
finalize the server copies the base's unchanged file entries, adds the
uploaded ones and checks the result against the path count and digest the
client declared, so the stored snapshot equals what a full upload builds.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from yoke_contracts.path_snapshot import KIND_FILE, snapshot_path_digest
from yoke_contracts.path_snapshot_chunks import (
    PathSnapshotChunkSyncPayload,
    PathSnapshotDelta,
)
from yoke_core.domain import db_backend
from yoke_core.domain.path_snapshot_content_rows import find_content_snapshot_id
from yoke_core.domain.project_snapshot_sync_refusals import SnapshotBaseMismatchError


def _p(conn: Any) -> str:
    return "%s" if db_backend.connection_is_postgres(conn) else "?"


def select_base_commit(
    conn: Any, project_id: int, candidates: Sequence[str]
) -> Optional[str]:
    """The first candidate commit with a stored content snapshot, or None."""
    wanted = [sha for sha in dict.fromkeys(candidates) if sha]
    if not wanted:
        return None
    p = _p(conn)
    marks = ", ".join(p for _ in wanted)
    rows = conn.execute(
        "SELECT DISTINCT s.commit_sha FROM path_snapshots s "
        f"WHERE s.project_id = {p} AND s.commit_sha IN ({marks}) AND EXISTS ("
        "  SELECT 1 FROM path_snapshot_entries e "
        "  JOIN path_targets t ON t.id = e.target_id "
        f"  WHERE e.snapshot_id = s.id AND t.kind = {p})",
        (project_id, *wanted, KIND_FILE),
    ).fetchall()
    held = {str(row[0]) for row in rows}
    return next((sha for sha in wanted if sha in held), None)


def offer_base(
    conn: Any,
    project_id: int,
    payload: PathSnapshotChunkSyncPayload,
    lane_head_recorded: bool,
) -> Dict[str, Any]:
    """Answer a base-offer begin; nothing is staged for this upload id."""
    assert payload.snapshot is not None
    base = select_base_commit(conn, project_id, payload.snapshot.base_candidates)
    conn.commit()
    return {
        "status": "base_selected",
        "upload_id": payload.upload_id,
        "base_commit_sha": base,
        "lane_head_recorded": lane_head_recorded,
    }


def apply_snapshot_delta(
    conn: Any,
    project_id: int,
    uploaded: List[Dict[str, Any]],
    delta: PathSnapshotDelta,
) -> List[Dict[str, Any]]:
    """The complete file list: base entries, minus removals, plus uploads."""
    base = delta.base_commit_sha
    base_id = find_content_snapshot_id(conn, project_id, base)
    if base_id is None:
        raise SnapshotBaseMismatchError(
            f"stored snapshot for base commit {base} is no longer available"
        )
    replaced = {str(entry["path"]) for entry in uploaded}
    replaced.update(delta.deleted_paths)
    files = [
        entry
        for entry in _base_file_entries(conn, base_id)
        if entry["path"] not in replaced
    ]
    files.extend(uploaded)
    paths = [str(entry["path"]) for entry in files]
    digest = snapshot_path_digest(paths)
    if len(paths) != delta.path_count or digest != delta.path_digest:
        raise SnapshotBaseMismatchError(
            f"stored snapshot for base commit {base} plus the uploaded changes "
            f"gives {len(paths)} files (digest {digest}); the client scanned "
            f"{delta.path_count} files (digest {delta.path_digest})"
        )
    return files


def _base_file_entries(conn: Any, snapshot_id: int) -> List[Dict[str, Any]]:
    p = _p(conn)
    rows = conn.execute(
        "SELECT t.path_string, e.line_count, e.language, e.module_name, "
        "e.dependency_edges FROM path_snapshot_entries e "
        "JOIN path_targets t ON t.id = e.target_id "
        f"WHERE e.snapshot_id = {p} AND t.kind = {p}",
        (snapshot_id, KIND_FILE),
    ).fetchall()
    return [
        {
            "path": str(row[0]),
            "line_count": int(row[1] or 0),
            "language": row[2],
            "module_name": row[3],
            "dependency_edges": json.loads(row[4]) if row[4] else [],
        }
        for row in (tuple(raw) for raw in rows)
    ]


__all__ = [
    "apply_snapshot_delta",
    "offer_base",
    "select_base_commit",
]
