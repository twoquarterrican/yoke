"""Which stored path snapshots carry file contents.

A snapshot answers path questions only when its entries hold the commit's
files. A row holding just the root directory carries no contents: it names
a commit without saying what that commit contains. Every snapshot reader
that would reuse a row for its commit goes through here, so a content-less
row is never mistaken for the commit's inventory. A content build for that
commit discards it first, because resolution reads any newer snapshot that
lacks a path as that path having disappeared.
"""

from __future__ import annotations

from typing import Any, Optional

from yoke_contracts.path_snapshot import KIND_FILE
from yoke_core.domain import db_backend


def _p(conn: Any) -> str:
    return "%s" if db_backend.connection_is_postgres(conn) else "?"


def find_content_snapshot_id(
    conn: Any, project_id: int, commit_sha: str
) -> Optional[int]:
    """Return the project's snapshot id for ``commit_sha`` if it has files."""
    p = _p(conn)
    row = conn.execute(
        "SELECT s.id FROM path_snapshots s "
        f"WHERE s.project_id = {p} AND s.commit_sha = {p} AND EXISTS ("
        "  SELECT 1 FROM path_snapshot_entries e "
        "  JOIN path_targets t ON t.id = e.target_id "
        f"  WHERE e.snapshot_id = s.id AND t.kind = {p})",
        (project_id, commit_sha, KIND_FILE),
    ).fetchone()
    if row is None:
        return None
    return int(row[0])


def discard_contentless_snapshot(conn: Any, project_id: int, commit_sha: str) -> None:
    """Delete the commit's snapshot row, which the caller proved content-less.

    Runs inside the caller's write transaction, after
    :func:`find_content_snapshot_id` returned ``None`` there.
    """
    p = _p(conn)
    snapshot = (
        f"SELECT id FROM path_snapshots WHERE project_id = {p} AND commit_sha = {p}"
    )
    for table in ("path_snapshot_symlink_facts", "path_snapshot_entries"):
        conn.execute(
            f"DELETE FROM {table} WHERE snapshot_id IN ({snapshot})",
            (project_id, commit_sha),
        )
    conn.execute(
        f"DELETE FROM path_snapshots WHERE project_id = {p} AND commit_sha = {p}",
        (project_id, commit_sha),
    )


__all__ = ["discard_contentless_snapshot", "find_content_snapshot_id"]
