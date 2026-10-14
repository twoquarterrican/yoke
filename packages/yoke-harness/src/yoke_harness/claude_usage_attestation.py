"""Read back the tokens a Claude session charged, child agents included.

Every assistant row of a Claude transcript carries a ``message.usage``
block. One logical response is written as several rows sharing a
``message.id`` and repeating the same usage, so the id is the dedup key
that keeps a turn from being counted once per content block.

A session's child agents write their own transcripts beside it
(:func:`yoke_harness.child_agent_artifacts.claude_child_transcripts`), in
the same row shape. Each file keeps its own resume offset, and all of
them share one message-id dedup set, so a row that appears in two files
— a child forked from the parent's context — is still counted once, and
a child file reread from the start after it shrank counts nothing twice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from yoke_contracts.harness_family_identity import CLAUDE_FAMILY
from yoke_contracts.session_usage_facts import (
    SessionUsage,
    normalize_count,
    unavailable,
)
from yoke_contracts.session_usage_sources import usage_source
from yoke_harness.artifact_scan import scan_rows
from yoke_harness.artifact_watermark import (
    ArtifactWatermark,
    load_watermark,
    partial_reason,
    save_watermark,
    stored_totals,
    watermark_lock,
)
from yoke_harness.child_agent_artifacts import claude_child_transcripts
from yoke_harness.claude_artifact_reader import (
    ASSISTANT_ROW_TYPE,
    claude_record_decoder,
    prepare_claude_watermark,
    stamp_claude_reader,
)
from yoke_harness.usage_attestation import (
    NO_ARTIFACT_REASON,
    _accumulate,
    _artifact,
    _reading,
    _text,
    _totals_by_model,
    _totals_document,
)


#: Stored map from a child transcript's file name to its resume offset.
CHILD_OFFSETS_KEY = "child_offsets"


def attest_claude_usage(
    payload: Mapping[str, Any], session_id: str, transcript_path: str
) -> SessionUsage:
    """Fold a Claude session's transcripts into per-model totals.

    A gap here means one assistant row's usage statement could not be
    read. An oversized row of any other kind is not a gap: it states no
    consumption, so the projection that dropped its content dropped
    nothing this fold was reading for.
    """
    source = usage_source(CLAUDE_FAMILY)
    path = _artifact(transcript_path or _text(payload.get("transcript_path")))
    if path is None:
        return unavailable(NO_ARTIFACT_REASON, source=source)
    with watermark_lock(session_id) as folding:
        if not folding:
            mark = load_watermark(session_id, path)
            return _reading(
                _totals_by_model(stored_totals(mark)),
                source=source,
                partial=partial_reason(mark),
            )
        mark = prepare_claude_watermark(load_watermark(session_id, path))
        stored = stored_totals(mark)
        totals = _totals_by_model(stored)
        seen = set(stored.get("message_ids", []))
        child_offsets = _child_offsets(stored)
        state: dict[str, Any] = {"gap": mark.oversized}

        def mark_gap() -> None:
            state["gap"] = True

        fold = _row_fold(totals, seen)
        scan = scan_rows(
            path,
            mark.offset,
            fold,
            record_factory=claude_record_decoder,
            on_unrecoverable=mark_gap,
        )
        caught_up = scan.caught_up
        for child in claude_child_transcripts(path):
            child_scan = scan_rows(
                child,
                _resume_offset(child, child_offsets.get(child.name, 0)),
                fold,
                record_factory=claude_record_decoder,
                on_unrecoverable=mark_gap,
            )
            child_offsets[child.name] = child_scan.offset
            caught_up = caught_up and child_scan.caught_up
        mark = ArtifactWatermark(
            offset=scan.offset,
            # One id per logical message, no rows or content. Evicting ids
            # would count compacted history again on a later incremental fold.
            totals=stamp_claude_reader(
                {
                    **_totals_document(totals),
                    "message_ids": sorted(seen),
                    CHILD_OFFSETS_KEY: child_offsets,
                }
            ),
            truncated=mark.truncated,
            oversized=bool(state["gap"]),
            caught_up=caught_up,
        )
        save_watermark(session_id, path, mark)
    return _reading(totals, source=source, partial=partial_reason(mark))


def _row_fold(
    totals: dict[str, dict[str, int]], seen: set[str]
) -> Callable[[Mapping[str, Any]], None]:
    """One row consumer shared by the parent and every child transcript."""

    def fold(row: Mapping[str, Any]) -> None:
        if row.get("type") != ASSISTANT_ROW_TYPE:
            return
        message = row.get("message")
        if not isinstance(message, dict):
            return
        key = _text(message.get("id")) or _text(row.get("requestId"))
        if not key or key in seen:
            return
        model = _text(message.get("model"))
        usage = message.get("usage")
        if not model or not isinstance(usage, dict):
            return
        seen.add(key)
        _accumulate(totals, model, _claude_buckets(usage))

    return fold


def _claude_buckets(usage: Mapping[str, Any]) -> dict[str, int]:
    """Convert one Claude usage block into the shared disjoint buckets.

    ``cache_creation`` states the same write total as
    ``cache_creation_input_tokens`` broken out by cache lifetime, so
    exactly one of the two is read: the split when it is present, because
    the lifetimes are billed at different rates, and the flat total
    otherwise. Reading both would count every cache write twice.
    """
    creation = usage.get("cache_creation")
    details = usage.get("output_tokens_details")
    if isinstance(creation, dict):
        short = normalize_count(creation.get("ephemeral_5m_input_tokens"))
        long_lived = normalize_count(creation.get("ephemeral_1h_input_tokens"))
    else:
        short = normalize_count(usage.get("cache_creation_input_tokens"))
        long_lived = 0
    return {
        "input": normalize_count(usage.get("input_tokens")),
        "cached_input": normalize_count(usage.get("cache_read_input_tokens")),
        "cache_write": short,
        "cache_write_long": long_lived,
        "output": normalize_count(usage.get("output_tokens")),
        "reasoning": normalize_count(
            details.get("thinking_tokens") if isinstance(details, dict) else None
        ),
    }


def _child_offsets(stored: Mapping[str, Any]) -> dict[str, int]:
    held = stored.get(CHILD_OFFSETS_KEY)
    if not isinstance(held, dict):
        return {}
    return {str(name): normalize_count(offset) for name, offset in held.items()}


def _resume_offset(child: Path, offset: int) -> int:
    """Where to resume a child file; a file that shrank rereads from zero.

    The shared dedup set already holds every message the earlier read
    counted, so rereading costs nothing twice.
    """
    try:
        return offset if child.stat().st_size >= offset else 0
    except OSError:
        return 0


__all__ = ["CHILD_OFFSETS_KEY", "attest_claude_usage"]
