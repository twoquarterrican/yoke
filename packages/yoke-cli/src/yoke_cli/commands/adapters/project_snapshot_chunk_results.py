"""Result rows the chunked snapshot-sync client reports for each snapshot."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from yoke_contracts.api.function_call import FunctionCallResponse, FunctionError
from yoke_contracts.path_snapshot import PathSnapshotPayload


def upload_result(
    source: Dict[str, Any],
    rows: List[Dict[str, Any]],
    warnings: List[str],
) -> FunctionCallResponse:
    return FunctionCallResponse(
        success=True,
        function="project.snapshot.sync",
        version="v1",
        result={
            "project_id": source.get("project_id"),
            "snapshots": rows,
            "warnings": list(warnings),
        },
    )


def deferral_response() -> FunctionCallResponse:
    return FunctionCallResponse(
        success=False,
        function="project.snapshot.sync",
        version="v1",
        error=FunctionError(
            code="snapshot_sync_deferred",
            message=(
                "large path snapshot deferred to keep this write fast; "
                "it uploads on the next `yoke project snapshot sync` "
                "(nothing is broken)"
            ),
        ),
    )


def begin_settled_row(
    snapshot: PathSnapshotPayload,
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """The begin's own row when it needed no chunks: reused or identity-only."""
    status = result.get("status")
    if status not in ("reused", "identity_only"):
        return None
    rows = result.get("snapshots") or []
    for row in rows:
        if row.get("commit_sha") == snapshot.commit_sha:
            return {
                **row,
                "status": status,
                "ref": snapshot.ref,
                "commit_sha": snapshot.commit_sha,
            }
    snapshot_id = result.get("snapshot_id")
    if snapshot_id is None:
        return None
    return {
        "status": "reused",
        "snapshot_id": snapshot_id,
        "ref": snapshot.ref,
        "commit_sha": snapshot.commit_sha,
        "entry_count": 0,
        "symlink_count": 0,
    }


def alias_snapshot_row(
    snapshot: PathSnapshotPayload,
    source_row: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "status": "reused",
        "snapshot_id": source_row.get("snapshot_id"),
        "ref": snapshot.ref,
        "commit_sha": snapshot.commit_sha,
        "entry_count": 0,
        "symlink_count": 0,
    }


__all__ = [
    "alias_snapshot_row",
    "begin_settled_row",
    "deferral_response",
    "upload_result",
]
