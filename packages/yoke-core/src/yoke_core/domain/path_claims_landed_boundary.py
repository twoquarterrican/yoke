"""Path-claim boundary proved from what an item's landing put on its target.

Before landing, the boundary is the lane's committed diff against the
moving integration target. After landing that question has a fixed answer,
and a gate evaluated then proves the boundary from it, with no lane and no
current remote head required.

The answer is the item's merge receipt for the landing: the files the lane
changed against the target as it stood immediately before the landing,
which the merge boundary records before it merges (the lane's merge-base
diff) or from the landed pull request's own file list. The landed commit's
first parent is not that boundary. A fast-forward of a lane whose tip merged
the target in has the lane's previous commit as first parent, so that diff
would hold everything the target gained since the lane last synced and
charge it to the item.

The landing applies while it still describes the item's current work: the
newest recorded landing, unless an active lane has since recorded a head
that is neither the landed candidate nor the merge (rework that has not
landed yet, which the lane-based check owns). The receipt applies when it
names that landing's candidate or merge commit on the landing's target. A
landing with no such receipt, or one whose receipt recorded no changed
files, is refused by name rather than guessed at from git history.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Sequence, Tuple
from yoke_core.domain.gate_satisfier_facts import OBSERVED_LANDED_MERGE
from yoke_core.domain.gate_satisfier_ladder import LadderResolution
from yoke_core.domain.gate_satisfier_ladder_catalog import (
    PATH_CLAIM_BOUNDARY_LADDER,
)
from yoke_core.domain.gate_satisfier_stamp import record_rung
from yoke_core.domain.item_landings import ItemLanding, landings_for_item
from yoke_core.domain.item_merge_receipt_document import newest_first, read_entries
from yoke_core.domain.item_worktrees import primary_item_worktree
from yoke_core.domain.path_claims import get_claim
from yoke_core.domain.path_claims_boundary_targets import path_strings_for_target_ids
from yoke_core.domain.project_identity import render_item_ref
from yoke_core.domain.schema_common import _table_exists

LANDED_MERGE_RUNG = "landed_merge"


class LandedBoundaryUnprovable(RuntimeError):
    """The landing has no recorded changed-file set to prove the boundary."""


def landing_for_boundary(conn: Any, item_id: int) -> Optional[ItemLanding]:
    """The landing that answers this item's boundary, or ``None`` before one.

    A database that has not converged ``item_landings`` has recorded no
    landing either, so it takes the lane-based check rather than failing.
    """
    if not _table_exists(conn, "item_landings"):
        return None
    landings = landings_for_item(conn, item_id)
    if not landings:
        return None
    newest = landings[-1]
    lane = primary_item_worktree(conn, item_id) or {}
    head = str(lane.get("commit_sha") or "")
    if head and head not in (newest.candidate_sha, newest.merge_sha):
        return None
    return newest


def _norm(sha: Any) -> str:
    return str(sha or "").strip().lower()


def landed_touched_files(
    conn: Any, *, item_id: int, landing: ItemLanding
) -> Tuple[dict, list]:
    """Return ``(receipt_entry, touched_paths)`` for ``landing``.

    Raises :class:`LandedBoundaryUnprovable` when no receipt names the
    landing, or the one that does recorded no changed files.
    """
    landed = {_norm(landing.candidate_sha), _norm(landing.merge_sha)} - {""}
    for entry in newest_first(read_entries(conn, item_id)):
        target = str(entry.get("target") or "")
        if landing.target_branch and target != landing.target_branch:
            continue
        if not landed & {_norm(entry.get("commit_sha")), _norm(entry.get("merge_sha"))}:
            continue
        touched = [str(path) for path in entry.get("touched_files") or [] if path]
        if not touched:
            raise LandedBoundaryUnprovable(
                f"landed_boundary_receipt_files_missing: the merge receipt for "
                f"branch {entry.get('branch')!r} on {target!r} recorded no "
                "changed files"
            )
        return entry, list(dict.fromkeys(touched))
    raise LandedBoundaryUnprovable(
        "landed_boundary_receipt_missing: no merge receipt on the item names "
        f"candidate {landing.candidate_sha or '(none)'} or merge "
        f"{landing.merge_sha} on {landing.target_branch or '(any target)'!r}"
    )


def _declared_coverage(conn: Any, claim_ids: Sequence[int]) -> Tuple[set, set]:
    declared: set = set()
    targets: set = set()
    for claim_id in claim_ids:
        claim = get_claim(conn, claim_id)
        targets.add(str(claim.get("integration_target") or ""))
        ids = [int(tid) for tid in claim.get("target_ids") or []]
        declared.update(path_strings_for_target_ids(conn, ids))
    return declared, targets


def _blocked(message: str) -> dict:
    return {
        "success": False,
        "error_code": "GATE_PATH_CLAIM_BOUNDARY",
        "error": message,
    }


def check_landed_boundary(
    conn: Any,
    *,
    item_id: int,
    target_status: str,
    claim_ids: Sequence[int],
    landing: ItemLanding,
) -> Optional[dict]:
    """Prove the boundary from ``landing``; ``None`` clears the gate."""
    ref = render_item_ref(conn, item_id)
    declared, targets = _declared_coverage(conn, claim_ids)
    if landing.target_branch and targets - {landing.target_branch}:
        return _blocked(
            f"{ref} landed merge {landing.merge_sha} on {landing.target_branch!r}, "
            f"but its path claims integrate into {sorted(targets)}; that landing "
            "cannot prove their coverage. Amend the claims' integration target "
            "or land the item on the claimed target, then retry the transition."
        )
    try:
        entry, touched = landed_touched_files(conn, item_id=item_id, landing=landing)
    except LandedBoundaryUnprovable as exc:
        return _blocked(
            f"{ref} landed as {landing.merge_sha}, but the boundary cannot be "
            f"proved from it: {exc}. Re-run the same close-out "
            f"(`yoke merge item {ref} ...`) from a checkout of the project; it "
            "re-records the receipt's changed files from the landed pull "
            "request or merge. If it still refuses, the landing left nothing to "
            "derive them from: send this refusal to steering "
            "(`yoke say --steering`) rather than widening claims to guess."
        )
    undeclared = sorted(set(touched) - declared)
    if undeclared:
        return _blocked(
            f"Path-claim boundary check blocked transition to {target_status!r}: "
            f"landing {landing.merge_sha} (merge receipt for branch "
            f"{entry.get('branch')!r}, changed against {landing.target_branch!r} "
            f"before it landed) changed {len(undeclared)} file(s) outside "
            f"{ref}'s declared coverage: {', '.join(undeclared)}.\n\nThe work has "
            "already landed, so widen the claim to cover what landed "
            "(`yoke claims path widen --claim-id N --add-paths ...`), then re-run the same close-out."
        )
    fact = {
        "merge_sha": landing.merge_sha,
        "candidate_sha": landing.candidate_sha,
        "receipt_branch": str(entry.get("branch") or ""),
        "receipt_commit_sha": str(entry.get("commit_sha") or ""),
        "source": "merge_receipt",
        "touched_paths": sorted(touched),
    }
    record_rung(
        conn,
        item_id=item_id,
        ladder=PATH_CLAIM_BOUNDARY_LADDER,
        resolution=LadderResolution(
            obligation=PATH_CLAIM_BOUNDARY_LADDER.obligation,
            rung=PATH_CLAIM_BOUNDARY_LADDER.rung(LANDED_MERGE_RUNG),
            facts={OBSERVED_LANDED_MERGE: json.dumps(fact, sort_keys=True)},
        ),
        target_status=target_status,
    )
    return None


__all__ = [
    "LANDED_MERGE_RUNG",
    "LandedBoundaryUnprovable",
    "check_landed_boundary",
    "landed_touched_files",
    "landing_for_boundary",
]
