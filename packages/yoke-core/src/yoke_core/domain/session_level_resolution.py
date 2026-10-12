"""Resolve current model/effort thresholds from observed facts and project Levels."""

from __future__ import annotations
from typing import Any, Optional, Sequence
from yoke_contracts.levels import Level, LevelsError, default_levels, level_for_session
from yoke_contracts.session_level import UNRESOLVED_EXECUTION_LEVEL
from yoke_contracts.session_model_facts import CLAUDE_CONTEXT_TIER_SUFFIX
from yoke_contracts.session_control.native_model_parsers import cursor_token_effort


def session_levels(conn: Any, project_id: Optional[int]) -> tuple[Level, ...]:
    """Return the levels a session in ``project_id`` is labeled against.

    Stored documents are validated at write time; one that no longer reads
    (a raw edit) labels nothing rather than refusing every registration,
    and ``yoke projects level-summary get`` names the repair.
    """
    if conn is None:
        return default_levels()
    from yoke_core.domain.universe_levels import UniverseLevelsError, effective_levels

    try:
        return effective_levels(conn, project_id)[0]
    except (LevelsError, UniverseLevelsError):
        return ()


def routing_model_of(
    served_model: Optional[str], requested_model: Optional[str]
) -> Optional[str]:
    """Return the model an option is matched against.

    A provider-attested model wins. Most sessions have none at registration,
    so the ask is the fallback, with its context-tier suffix removed because
    that suffix names a context window rather than a different model.
    """
    if served_model and served_model.strip():
        return served_model.strip()
    asked = (requested_model or "").strip()
    if asked.lower().endswith(CLAUDE_CONTEXT_TIER_SUFFIX):
        asked = asked[: -len(CLAUDE_CONTEXT_TIER_SUFFIX)]
    return asked or None


def routing_effort_of(
    served_effort: Optional[str],
    requested_effort: Optional[str],
    served_model: Optional[str] = None,
) -> Optional[str]:
    """Return the effort an option is matched against, attested first."""
    for value in (
        served_effort,
        cursor_token_effort(served_model or ""),
        requested_effort,
    ):
        if value and value.strip():
            return value.strip().lower()
    return None


def resolve_execution_level(
    *,
    executor: str,
    explicit_level: Optional[str],
    levels: Sequence[Level],
    model: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    records: Sequence[Any] = (),
) -> str:
    """Resolve actual model facts; a launch's level stamp is never capability."""
    matched = level_for_session(
        levels,
        executor=executor,
        model=model,
        reasoning_effort=reasoning_effort,
        records=records,
    )
    return matched or UNRESOLVED_EXECUTION_LEVEL
