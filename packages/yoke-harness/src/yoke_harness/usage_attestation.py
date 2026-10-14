"""Read back the tokens a provider actually charged a harness session.

One entry point, :func:`attest_session_usage`, dispatches to the artifact
each harness writes for itself, exactly as model attestation does. Every
branch answers only from that artifact and converts its source's
semantics into the shared disjoint buckets before returning, so nothing
downstream has to remember which provider counts what.

What each harness reports, measured rather than assumed:

* **claude** — every assistant row of its transcript carries a
  ``message.usage`` block stating uncached input, cache reads, cache
  writes split by cache lifetime, output, and the thinking tokens inside
  that output, read by :mod:`yoke_harness.claude_usage_attestation`.
* **codex** — its rollout carries cumulative ``token_count`` events, read
  by :mod:`yoke_harness.codex_usage_attestation`.
* **cursor** — optional ``stop`` / ``afterAgentResponse`` token fields
  (inclusive ``input_tokens``) and print-mode result ``usage`` (exclusive
  ``inputTokens``), the latter presented by the reader of a finished
  native's capture rather than by a hook, read by
  :mod:`yoke_harness.cursor_usage_attestation`.

A session's child agents are charged to it on every harness. Where each
harness keeps a child's usage is named in
:mod:`yoke_harness.child_agent_artifacts`; every reader folds what it
finds there into the same per-model totals (:func:`_accumulate`) that
the parent's own calls fill, so one pricing covers both. Calls a harness
never writes a usage row for — context compaction and summarization —
cannot be counted and are not estimated
(:data:`yoke_contracts.session_usage_sources.UNRECORDED_USAGE_UNDERCOUNT`).

Three differences between those branches are deliberate, and each
follows from what its source actually states. Claude accumulates, so its
fold dedups per message and a replay must start from empty totals; Codex
does not accumulate at all, so its newest cumulative statement replaces
whatever is held and a lost record costs the model history rather than
the counts; Cursor is folded from payloads handed to this process once,
so its reader waits for the lock rather than yielding it, and a payload
that omits the optional token fields is unavailable for that surface
rather than a zero.

Reads resume from a per-session watermark, so a hook event folds only
what the artifact gained since the last one, and each fold streams its
records under the shared byte bounds rather than holding a tail whose
size is the session's to choose. Only one fold per session runs at a
time: a second hook arriving mid-fold answers from the totals already
persisted instead of scanning the same bytes again.
"""

from __future__ import annotations

from datetime import datetime
from yoke_contracts.timestamps import utc_now
from pathlib import Path
from typing import Any, Mapping, Optional

from yoke_contracts.session_usage_facts import (
    USAGE_FIELDS,
    USAGE_COMPLETE,
    ModelUsage,
    SessionUsage,
    normalize_count,
    unavailable,
    with_partial,
)


#: Recorded when an artifact exists but has not yet stated any usage.
NO_USAGE_YET_REASON = "the harness artifact states no consumption yet"

#: Recorded when the artifact naming this session cannot be found.
NO_ARTIFACT_REASON = "no harness artifact was found for this session"


def attest_session_usage(
    executor: str,
    payload: Mapping[str, Any],
    *,
    transcript_path: str = "",
) -> SessionUsage:
    """Return the consumption this session's own artifact proves."""
    from yoke_harness.hooks.identity_runtime import is_claude, is_codex, is_cursor

    try:
        if is_cursor(executor):
            from yoke_harness.cursor_usage_attestation import attest_cursor_usage

            return attest_cursor_usage(payload)
        session_id = _text(payload.get("session_id"))
        if is_codex(executor):
            from yoke_harness.codex_usage_attestation import attest_codex_usage

            return attest_codex_usage(payload, session_id)
        if is_claude(executor):
            from yoke_harness.claude_usage_attestation import attest_claude_usage

            return attest_claude_usage(payload, session_id, transcript_path)
    except Exception:  # noqa: BLE001 — an unreadable source attests nothing
        return unavailable("the harness artifact could not be read")
    return unavailable(f"no usage source is declared for {executor}")


def _reading(
    totals: dict[str, dict[str, int]], *, source: str, partial: Optional[str]
) -> SessionUsage:
    """Compose one reading from folded per-model totals."""
    models = tuple(
        ModelUsage(
            model=model, **{field: counts.get(field, 0) for field in USAGE_FIELDS}
        )
        for model, counts in totals.items()
        if model
    )
    if not models:
        return _empty_reading(source, partial)
    reading = SessionUsage(
        status=USAGE_COMPLETE,
        observed_at=_observed_at(),
        source=source,
        models=models,
    )
    return with_partial(reading, partial) if partial else reading


def _empty_reading(source: str, partial: Optional[str]) -> SessionUsage:
    """An artifact that exists but has stated nothing yet."""
    return unavailable(partial or NO_USAGE_YET_REASON, source=source)


def _totals_by_model(stored: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    models = stored.get("models")
    if not isinstance(models, dict):
        return {}
    return {
        str(model): {
            field: normalize_count(counts.get(field)) for field in USAGE_FIELDS
        }
        for model, counts in models.items()
        if isinstance(counts, dict)
    }


def _totals_document(totals: Mapping[str, dict[str, int]]) -> dict[str, Any]:
    return {"models": {model: dict(counts) for model, counts in totals.items()}}


def _accumulate(
    totals: dict[str, dict[str, int]], model: str, counts: Mapping[str, int]
) -> None:
    entry = totals.setdefault(model, {field: 0 for field in USAGE_FIELDS})
    for field in USAGE_FIELDS:
        entry[field] += counts.get(field, 0)


def _artifact(path: str) -> Optional[Path]:
    if not path:
        return None
    resolved = Path(path)
    return resolved if resolved.is_file() else None


def _observed_at() -> datetime:
    return utc_now()


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = [
    "NO_ARTIFACT_REASON",
    "NO_USAGE_YET_REASON",
    "attest_session_usage",
]
