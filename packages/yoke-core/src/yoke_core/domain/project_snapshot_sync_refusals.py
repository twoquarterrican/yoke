"""Named refusals of a chunked project snapshot sync.

Each carries the error ``code`` the handler answers with and the recovery
the client or operator follows, so the handler maps them in one place and a
client can act on the code rather than on message text.
"""

from __future__ import annotations

from yoke_contracts.path_snapshot_chunks import (
    SNAPSHOT_BASE_MISMATCH_CODE,
    SNAPSHOT_CHUNK_UPLOAD_MISSING_CODE,
)


class SnapshotSyncRefusal(ValueError):
    """A chunked-sync refusal the client can act on by its ``code``."""

    code = "snapshot_sync_failed"
    recovery_hint = "Repair with `yoke project snapshot sync`."


class SnapshotBaseMismatchError(SnapshotSyncRefusal):
    """The stored base cannot reproduce the tree the client scanned."""

    code = SNAPSHOT_BASE_MISMATCH_CODE
    recovery_hint = (
        "Upload the full inventory: the client restarts without a base. "
        "If this repeats, run `yoke project snapshot sync` and report the "
        "base commit named here."
    )


class ChunkUploadMissingError(SnapshotSyncRefusal):
    """The staged upload is gone; the caller must restart it from ``begin``.

    Staging rows are deleted on abort and on a completed finalize, so a
    retried append or finalize whose response was lost finds nothing. That
    is recoverable by re-uploading, unlike the other chunk failures, so it
    carries its own type instead of collapsing into a generic failure.
    """

    code = SNAPSHOT_CHUNK_UPLOAD_MISSING_CODE
    recovery_hint = (
        "Restart the chunked upload from `begin`; nothing was staged for "
        "this upload id."
    )


__all__ = [
    "ChunkUploadMissingError",
    "SnapshotBaseMismatchError",
    "SnapshotSyncRefusal",
]
