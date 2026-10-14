"""Session analytics constants, registry seeding, and base emitters."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from yoke_contracts.machine_config.settings_keys import (
    SESSION_STALE_TTL_WITH_HOLDINGS_KEY,
    machine_setting_default,
)

from yoke_contracts.skill_registry import STAGE_SKILL_IDS

from .runtime_settings import get_int

logger = logging.getLogger(__name__)


class SessionError(Exception):
    """Raised when a session operation violates a business rule."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Constants — TTLs sourced from machine config so prose/code share one tunable.
# ---------------------------------------------------------------------------

DEFAULT_STALE_THRESHOLD_MINUTES = get_int("session_stale_ttl_minutes", 20)
DEFAULT_STALE_WITH_HOLDINGS_THRESHOLD_MINUTES = get_int(
    SESSION_STALE_TTL_WITH_HOLDINGS_KEY,
    int(machine_setting_default(SESSION_STALE_TTL_WITH_HOLDINGS_KEY)),
)
DEFAULT_PROGRESS_THRESHOLD_MINUTES = 90


# ---------------------------------------------------------------------------
# Event names — registered in event_registry
# ---------------------------------------------------------------------------

EVENT_HARNESS_SESSION_STARTED = "HarnessSessionStarted"
EVENT_HARNESS_SESSION_ENDED = "HarnessSessionEnded"
EVENT_WORK_CLAIMED = "WorkClaimed"
EVENT_WORK_RELEASED = "WorkReleased"
EVENT_WORK_RECLAIMED = "WorkReclaimed"
EVENT_RECLAIM_ABORTED = "ReclaimAborted"
EVENT_WORK_HANDED_OFF = "WorkHandedOff"
EVENT_CHAIN_STEP_COMPLETED = "ChainStepCompleted"


EVENT_HARNESS_SESSION_HOOK_FAILED = "HarnessSessionHookFailed"
EVENT_HARNESS_SESSION_STALE_RECLAIMED = "HarnessSessionStaleReclaimed"
EVENT_HARNESS_SESSION_END_REJECTED_ACTIVE_CLAIM = "HarnessSessionEndRejectedActiveClaim"
EVENT_OPERATOR_CLAIM_OVERRIDE = "OperatorClaimOverride"
EVENT_HARNESS_SESSION_STALE_SWEEP_COMPLETED = "HarnessSessionStaleSweepCompleted"
EVENT_HARNESS_SESSION_END_RELEASED_CLAIMS = "HarnessSessionEndReleasedClaims"
EVENT_ITEM_CLAIM_RELEASE_FAILED = "ItemClaimReleaseFailed"
EVENT_SESSION_REACTIVATED_WITH_RELEASED_CLAIMS = "SessionReactivatedWithReleasedClaims"
EVENT_SESSION_REACTIVATION_REACQUIRED_CLAIMS = "SessionReactivationReacquiredClaims"
EVENT_HARNESS_SESSION_RESUME_BLOCK_SHOWN = "HarnessSessionResumeBlockShown"


# ---------------------------------------------------------------------------
# Event emission helper — native Python emitter
# ---------------------------------------------------------------------------


def _emit_event(
    event_name: str,
    *,
    event_kind: str,
    event_type: str,
    source_type: str,
    session_id: str,
    project: Optional[str] = None,
    item_id: Optional[str] = None,
    task_num: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
    outcome: str = "completed",
    severity: str = "INFO",
) -> None:
    """Emit a structured event via the native Python emitter (non-fatal).

    Delegates to ``yoke_core.domain.events.emit_event`` which writes
    directly to the ``events`` table.  Falls back silently on any failure.
    """
    try:
        from .events import emit_event as _native_emit

        _native_emit(
            event_name,
            event_kind=event_kind,
            event_type=event_type,
            source_type=source_type,
            session_id=session_id,
            project=project or "",
            severity=severity,
            outcome=outcome,
            item_id=item_id,
            task_num=task_num,
            context=context,
        )
    except Exception as exc:
        logger.debug("Native event emission failed for %s: %s", event_name, exc)


def _emit_session_event(
    event_name: str,
    *,
    session_id: str,
    item_id: Optional[str] = None,
    task_num: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
    outcome: str = "completed",
) -> None:
    """Emit a structured session event via the native Python emitter (non-fatal).

    Events are best-effort telemetry — failures are logged but never
    propagate to the caller.

    Args:
        event_name: Registered event name (e.g., ``WorkClaimed``).
        session_id: Session correlation ID.
        item_id: Top-level indexed ``item_id`` (stored bare numeric when possible).
            Populated when the event targets a specific work unit.
        task_num: Top-level indexed ``task_num`` for epic task context.
        context: Envelope detail dict (serialised to JSON).
        outcome: Event outcome string (default ``completed``).
    """
    _emit_event(
        event_name,
        event_kind="system",
        event_type="session_lifecycle",
        source_type="backend",
        session_id=session_id,
        item_id=item_id,
        task_num=task_num,
        context=context,
        outcome=outcome,
    )


# ---------------------------------------------------------------------------
# Shared downstream dispatch paths
# ---------------------------------------------------------------------------

# Claims and dispatch consume the same current stage-skill inventory.
_NEXT_STEP_TO_PATH: Dict[str, str] = {
    skill_id: skill_id for skill_id in STAGE_SKILL_IDS
}


def lifecycle_dispatch_paths() -> frozenset:
    """Return current stage-skill paths supported by the scheduler."""
    return STAGE_SKILL_IDS
