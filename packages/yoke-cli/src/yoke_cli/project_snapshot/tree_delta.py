"""Incremental snapshot scans: read only blobs that differ from a base.

The server already holds the snapshot of some ancestor commit. Comparing
two ``git ls-tree`` listings by (mode, blob id) names exactly the files
that changed, so only those are read and parsed. Symlink facts depend on
the whole path set, so every symlink is read and its facts sent in full.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from yoke_cli.project_snapshot.scanner import (
    ProjectSnapshotScanError,
    ls_tree,
    run_git,
    scan_blobs,
    scan_ref,
    symlink_facts,
)
from yoke_cli.project_snapshot.sync_refs import SyncRef
from yoke_contracts.path_snapshot import (
    SnapshotFileEntry,
    SnapshotSymlinkFact,
    snapshot_path_digest,
)
from yoke_contracts.path_snapshot_chunks import (
    SNAPSHOT_BASE_CANDIDATE_LIMIT,
    PathSnapshotDelta,
)

SYMLINK_MODE = "120000"


@dataclass(frozen=True)
class SnapshotUpload:
    """What one chunked upload sends: files, symlinks, and maybe a delta."""

    label: str
    commit_sha: str
    files: List[SnapshotFileEntry]
    symlinks: List[SnapshotSymlinkFact] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    delta: Optional[PathSnapshotDelta] = None


def base_candidates(
    repo_root: Path,
    commit_sha: str,
    integration_sha: Optional[str] = None,
) -> List[str]:
    """Commits to offer as a base, the likeliest smallest diff first.

    The commit's own first-parent ancestors come first; for a lane, the
    integration target and the merge base are offered right after the
    lane's own commits, ahead of older history below the merge base.
    """
    ancestors = _first_parent_ancestors(repo_root, commit_sha)
    preferred: List[str] = []
    if integration_sha and integration_sha != commit_sha:
        merge_base = _merge_base(repo_root, commit_sha, integration_sha)
        cut = ancestors.index(merge_base) if merge_base in ancestors else 0
        preferred = [*ancestors[:cut], integration_sha]
        if merge_base:
            preferred.append(merge_base)
        ancestors = ancestors[cut:]
    ordered = dict.fromkeys(sha for sha in [*preferred, *ancestors] if sha)
    ordered.pop(commit_sha, None)
    return list(ordered)[:SNAPSHOT_BASE_CANDIDATE_LIMIT]


def scan_full(repo_root: Path, ref: SyncRef) -> SnapshotUpload:
    payload = scan_ref(
        repo_root,
        ref.commit_sha,
        label=ref.label,
        expected_sha=ref.commit_sha,
        warnings=ref.warnings,
    )
    return SnapshotUpload(
        label=ref.label,
        commit_sha=ref.commit_sha,
        files=payload.files,
        symlinks=payload.symlinks,
        warnings=payload.warnings,
    )


def scan_delta(repo_root: Path, ref: SyncRef, base_sha: str) -> SnapshotUpload:
    """Scan only the files of ``ref`` whose blob differs from ``base_sha``."""
    entries = ls_tree(repo_root, ref.commit_sha)
    base = {
        path: (mode, sha)
        for mode, kind, sha, path in ls_tree(repo_root, base_sha)
        if kind == "blob"
    }
    blobs = [(mode, sha, path) for mode, kind, sha, path in entries if kind == "blob"]
    paths = [path for _mode, _sha, path in blobs]
    changed = [
        (sha, path) for mode, sha, path in blobs if base.get(path) != (mode, sha)
    ]
    changed_paths = {path for _sha, path in changed}
    links = [
        (sha, path)
        for mode, sha, path in blobs
        if mode == SYMLINK_MODE and path not in changed_paths
    ]
    parsed, sources = scan_blobs(repo_root, [*changed, *links], ref.label)
    files = [entry for entry in parsed if entry.path in changed_paths]
    return SnapshotUpload(
        label=ref.label,
        commit_sha=ref.commit_sha,
        files=files,
        symlinks=symlink_facts(entries, sources),
        warnings=ref.warnings,
        delta=PathSnapshotDelta(
            base_commit_sha=base_sha,
            deleted_paths=sorted(set(base) - set(paths)),
            path_count=len(paths),
            path_digest=snapshot_path_digest(paths),
        ),
    )


def _first_parent_ancestors(repo_root: Path, commit_sha: str) -> List[str]:
    proc = run_git(
        repo_root,
        "rev-list",
        "--first-parent",
        f"--max-count={SNAPSHOT_BASE_CANDIDATE_LIMIT + 1}",
        commit_sha,
    )
    return [line for line in proc.stdout.split()[1:] if line]


def _merge_base(repo_root: Path, left: str, right: str) -> Optional[str]:
    try:
        proc = run_git(repo_root, "merge-base", left, right)
    except ProjectSnapshotScanError:
        return None
    return proc.stdout.strip() or None


__all__ = [
    "SnapshotUpload",
    "base_candidates",
    "scan_delta",
    "scan_full",
]
