"""The commits one candidate added since the previous release, from one comparison.

Custody asks, per merged item, whether the run's candidate contains the item's
landing. Asked of the repository provider one item at a time, that is up to
three GitHub reads per item. Almost every deliverable landing is a commit the
candidate added since the previous release, and one comparison over that range
lists all of them, so the per-item question becomes a set lookup.

The answer is only ever a positive shortcut. A landing on the range's
first-parent line is reachable from the candidate, so it is contained. A
landing outside it may still be contained (it predates the range, or arrived
under another commit id), so callers ask the per-item question for those, and
a range that cannot be read is an empty set rather than a refusal.
"""

from __future__ import annotations

from typing import Any

from yoke_core.domain.deployment_run_carried_work_source import (
    RELATION_DIVERGED,
    CarriedWorkSourceUnavailable,
    open_carried_work_source,
)
from yoke_core.domain.schema_read_scope import shared_read


def candidate_range_commits(
    conn: Any, project_id: int, *, base: str, candidate: str
) -> frozenset[str]:
    """Commits on ``candidate``'s first-parent line since ``base``, lowercased.

    Shared inside one composition operation, so every reader of the same
    project and candidate pays for one comparison.
    """
    base = str(base or "").strip()
    candidate = str(candidate or "").strip()
    if not base or not candidate:
        return frozenset()

    def read() -> frozenset[str]:
        try:
            source = open_carried_work_source(conn, int(project_id))
            start = source.resolve_commit(base)
            head = source.resolve_commit(candidate)
            if not start or not head:
                return frozenset()
            commits = source.commit_range(start, head)
        except CarriedWorkSourceUnavailable:
            # The per-item question still runs and names this refusal.
            return frozenset()
        if commits.relation == RELATION_DIVERGED:
            return frozenset()
        return frozenset(commit.lower() for commit in commits.commits)

    key = ("candidate_range_commits", int(project_id), base, candidate)
    return shared_read(conn, key, read)


__all__ = ["candidate_range_commits"]
