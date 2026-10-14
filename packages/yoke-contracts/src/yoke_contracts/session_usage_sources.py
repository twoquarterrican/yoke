"""Where each harness states the tokens it consumed, or that it states none.

``harness_sessions.usage_totals`` promises a measurement, so only a
surface that counts tokens outright may fill it. A count inferred from
transcript length, message count, or a context-window percentage would
file an estimate under that promise. A harness with no such surface
attests nothing and says so here, so a missing reading reads as a
declared gap rather than a branch someone forgot to write.
"""

from __future__ import annotations

from typing import Mapping

from yoke_contracts.harness_family_identity import (
    CLAUDE_FAMILY,
    CODEX_FAMILY,
    CURSOR_FAMILY,
)


#: Why a Cursor payload that named some token fields but not all four is
#: not folded: the missing ones are unknown, not fabricated zeros.
CURSOR_INCOMPLETE_TOKEN_FIELDS_REASON = (
    "cursor payload named some token fields but not the complete set"
)

#: Why token fields without ``generation_id`` or ``request_id`` are not
#: folded: the same parent turn can arrive twice, and without an id the
#: second copy cannot be distinguished from a new turn.
CURSOR_NO_TURN_IDENTITY_REASON = (
    "cursor token fields arrived without generation_id or request_id"
)

#: Stored model name when a reading's source named no model — a Cursor
#: payload that carries none, or a Codex rollout whose model statement
#: could not be read. Empty strings are dropped by ``usage_from_document``
#: and by the per-model reading builder, so the sentinel must be
#: non-empty: without it, exactly measured tokens would disappear for
#: want of a label, which is worse than pricing them as unattributable.
UNNAMED_MODEL = "unknown"

#: The standing known undercount of every harness's reading. Session
#: totals include each child agent's (subagent's) calls on every harness,
#: but a call the harness never writes a usage row for — context
#: compaction or summarization — leaves nothing to count. Those calls are
#: not estimated, because ``usage_totals`` promises measurement.
UNRECORDED_USAGE_UNDERCOUNT = (
    "includes child-agent usage; context compaction and summarization calls "
    "that write no usage row are not counted, so this can undercount"
)

#: Cursor's first-class usage surface: turn hook fields, and the
#: print-mode result ``usage`` object read from a finished native's own
#: capture, because that result is printed after the turn's last hook —
#: which is also why that capture retains its tail rather than only its
#: opening bytes.
#: Conversation-store blobs still carry no usage; a payload that omits the
#: optional fields is ``unavailable`` for that surface, not a global
#: "Cursor unsupported" deferral.
CURSOR_USAGE_SOURCE = (
    "cursor parent and child-agent turn stop/afterAgentResponse token fields; "
    "print-mode result usage"
)

#: The first-class usage surface per harness family, or ``""`` for a
#: family that counts tokens nowhere machine-readable.
#:
#: Claude stamps a full ``message.usage`` block on every assistant row of
#: its session transcript and of each child agent's transcript under the
#: session's ``subagents/`` directory, naming uncached input, cache reads,
#: cache writes split by cache lifetime, output, and the thinking tokens
#: inside that output. Codex writes a cumulative ``token_count`` event into
#: each thread's rollout whose ``info.total_token_usage`` is that thread's
#: consumption to that point; a child agent is its own thread. Cursor folds
#: optional turn token fields from ``stop`` / ``afterAgentResponse``,
#: child-agent turns included, and print-mode result ``usage`` — see
#: :data:`CURSOR_USAGE_SOURCE`. What none of them records is
#: :data:`UNRECORDED_USAGE_UNDERCOUNT`.
SESSION_USAGE_SOURCES: Mapping[str, str] = {
    CLAUDE_FAMILY: "transcript and child-agent transcript assistant message.usage",
    CODEX_FAMILY: "thread and child-thread rollout token_count info.total_token_usage",
    CURSOR_FAMILY: CURSOR_USAGE_SOURCE,
}


def states_usage(harness_id: object) -> bool:
    """True when *harness_id* has a first-class token-count source."""
    return bool(SESSION_USAGE_SOURCES.get(str(harness_id or "").strip()))


def usage_source(harness_id: object) -> str:
    """Return the artifact *harness_id* states its consumption in."""
    return SESSION_USAGE_SOURCES.get(str(harness_id or "").strip(), "")


__all__ = [
    "CURSOR_INCOMPLETE_TOKEN_FIELDS_REASON",
    "CURSOR_NO_TURN_IDENTITY_REASON",
    "UNNAMED_MODEL",
    "CURSOR_USAGE_SOURCE",
    "SESSION_USAGE_SOURCES",
    "UNRECORDED_USAGE_UNDERCOUNT",
    "states_usage",
    "usage_source",
]
