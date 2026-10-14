"""``HarnessSessionResumed`` event constant, payload, and emit helper.

Sibling to :mod:`sessions_analytics_core` (session event constants live there)
and :mod:`scheduler_events` (sibling emit helpers for adjacent
reactivation events). The dedicated event surfaces the resumption
marker — a single ``event_name`` predicate is enough to
locate the episode boundary on the events ledger, so audit callers no
longer have to introspect the ``HarnessSessionStarted`` envelope to
distinguish a fresh start from a resumption.

Episode-boundary query helpers consult both ``HarnessSessionResumed``
and ``HarnessSessionStarted`` rows; see
:mod:`yoke_core.domain.events_current_episode` for the shared
resolver.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence


_logger = logging.getLogger(__name__)


EVENT_HARNESS_SESSION_RESUMED = "HarnessSessionResumed"


def build_claim_details(
    *,
    released_claims: Sequence[Mapping[str, Any]],
    reacquired_claims: Sequence[Mapping[str, Any]],
    conflicts: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Render claim entries with explicit ``episode_scope`` tags.

    Order: inherited (released-but-not-reacquired) -> reacquired ->
    conflicts. Each entry carries the original target descriptor plus
    the scope label so audit callers can tell why a claim is in the
    current episode without joining against the work_claims table.
    """

    def _key(entry: Mapping[str, Any]):
        return (
            entry.get("target_kind"),
            json.dumps(
                entry.get("scope") or {},
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    reacquired_index = {_key(e): e for e in reacquired_claims}
    conflict_index = {_key(e): e for e in conflicts}

    details: List[Dict[str, Any]] = []
    for entry in released_claims:
        key = _key(entry)
        if key in reacquired_index:
            scope = "reacquired"
            extra = {
                k: v for k, v in reacquired_index[key].items() if k == "new_claim_id"
            }
        elif key in conflict_index:
            scope = "conflict"
            extra = {k: v for k, v in conflict_index[key].items() if k not in entry}
        else:
            scope = "inherited"
            extra = {}
        details.append({**dict(entry), "episode_scope": scope, **extra})

    existing_keys = {_key(d) for d in details}
    for entry in reacquired_claims:
        if _key(entry) in existing_keys:
            continue
        details.append({**dict(entry), "episode_scope": "reacquired"})
        existing_keys.add(_key(entry))

    for entry in conflicts:
        if _key(entry) in existing_keys:
            continue
        details.append({**dict(entry), "episode_scope": "conflict"})
        existing_keys.add(_key(entry))

    return details


def emit_session_resumed(
    *,
    session_id: str,
    released_claims: Sequence[Mapping[str, Any]],
    reacquired_claims: Sequence[Mapping[str, Any]],
    conflicts: Sequence[Mapping[str, Any]],
    prior_release_reason: str = "session_ended",
    project: str = "",
) -> Optional[str]:
    """Emit ``HarnessSessionResumed`` for a resumed-episode register pass.

    Every reactivation emits, including one whose session held no claims
    when the transient end closed it — the empty sequences then render as
    zero counts and an empty ``claim_details``. Returns the inserted event
    id on success, ``None`` on emission failure (telemetry is best-effort
    and never blocks the register path). The envelope keys are stable so
    audit consumers can rely on them.
    """
    try:
        from .events import emit_event

        context: Dict[str, Any] = {
            "session_id": session_id,
            "resumption": True,
            "prior_release_reason": prior_release_reason,
            "released_claim_count": len(released_claims),
            "reacquired_count": len(reacquired_claims),
            "conflict_count": len(conflicts),
            "claim_details": build_claim_details(
                released_claims=released_claims,
                reacquired_claims=reacquired_claims,
                conflicts=conflicts,
            ),
        }
        result = emit_event(
            EVENT_HARNESS_SESSION_RESUMED,
            event_kind="system",
            event_type="session_lifecycle",
            source_type="backend",
            session_id=session_id,
            project=project,
            context=context,
        )
    except Exception as exc:
        _logger.debug("%s emission failed: %s", EVENT_HARNESS_SESSION_RESUMED, exc)
        return None
    if result is not None and result.ok:
        return result.event_id
    return None


__all__ = [
    "EVENT_HARNESS_SESSION_RESUMED",
    "build_claim_details",
    "emit_session_resumed",
]
