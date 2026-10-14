"""Read back the tokens Codex charged one thread.

Codex states consumption as ``token_count`` rollout events whose
``info.total_token_usage`` is cumulative for the whole thread, so nothing
accumulates here: the newest statement replaces the previous one, and a
read that finds no new statement keeps what it had. Its input count
contains its cached input and its output count contains its reasoning,
both of which are converted into the shared disjoint buckets.

A child agent is its own thread with its own rollout and its own
cumulative total (:mod:`yoke_harness.child_agent_artifacts`). The fold
follows every child the parent names, and every child those children
name, keeping each thread's own offset and newest total in the parent's
record; the session's reading is the sum of every thread's total.

Reading resumes from the same per-session watermark every harness reader
uses, under the same one-fold-at-a-time lock: a hook arriving while
another is folding answers from the persisted totals rather than
scanning the rollout a second time.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Optional

from yoke_contracts.harness_family_identity import CODEX_FAMILY
from yoke_contracts.session_usage_facts import (
    SessionUsage,
    normalize_count,
    unavailable,
    with_cost_caveat,
)
from yoke_contracts.session_usage_sources import UNNAMED_MODEL, usage_source
from yoke_harness.artifact_scan import ScanResult, scan_rows
from yoke_harness.child_agent_artifacts import codex_child_thread_id
from yoke_harness.codex_artifact_reader import (
    MODEL_HISTORY_INCOMPLETE_KEY,
    USAGE_INCOMPLETE_KEY,
    codex_record_decoder,
    prepare_codex_watermark,
    stamp_codex_reader,
)
from yoke_harness.artifact_watermark import (
    ArtifactWatermark,
    load_watermark,
    partial_reason,
    save_watermark,
    stored_totals,
    watermark_lock,
)
from yoke_harness.usage_attestation import (
    NO_ARTIFACT_REASON,
    _accumulate,
    _empty_reading,
    _reading,
    _text,
)


#: Recorded when a thread states one cumulative total but ran more than
#: one model, so that total cannot be divided between them. The tokens
#: are still exactly what the thread consumed, which is why this names a
#: pricing caveat rather than a partial count.
MIXED_MODEL_REASON = (
    "this harness states one thread-wide total and more than one model "
    "served the thread, so consumption cannot be attributed per model"
)
USAGE_GAP_REASON = (
    "a Codex rollout record could not be projected, so its cumulative token "
    "statement is unavailable until a later total replaces it"
)
MODEL_HISTORY_GAP_REASON = (
    "a Codex rollout record could not be projected, so the session's model "
    "history and API-equivalent cost cannot be known exactly"
)
CHILD_ROLLOUT_MISSING_REASON = (
    "a child-agent thread this session spawned has no rollout file on this "
    "machine yet, so its consumption is not counted; the next fold looks again"
)

#: Stored map from a child thread id to that thread's own fold state.
CHILDREN_KEY = "children"
#: Set on a child thread whose rollout could not be found.
CHILD_MISSING_KEY = "rollout_missing"


def attest_codex_usage(payload: Mapping[str, Any], session_id: str) -> SessionUsage:
    """Read a Codex thread's newest cumulative total, plus its children's.

    Nothing accumulates within a thread: ``total_token_usage`` already
    covers the whole thread, so the newest statement replaces the previous
    one. Each child thread the session spawned states its own cumulative
    total in its own rollout, and those totals add to the parent's.
    """
    from yoke_harness.hooks.identity_runtime import resolve_session_id
    import json as _json

    source = usage_source(CODEX_FAMILY)
    thread_id = _text(payload.get("thread_id")) or resolve_session_id(
        _json.dumps(dict(payload))
    )
    path = _rollout(thread_id) if thread_id else None
    if path is None:
        return unavailable(NO_ARTIFACT_REASON, source=source)
    with watermark_lock(session_id) as folding:
        if not folding:
            return _persisted_codex_reading(session_id, path, source)
        persisted_mark = load_watermark(session_id, path)
        mark = prepare_codex_watermark(persisted_mark)
        stored = stored_totals(mark)
        scan, own, found = _fold_thread(path, mark.offset, stored)
        children, children_caught_up = _fold_children(
            _held_children(stored), found, root=thread_id
        )
        threads = [own, *children.values()]
        mark = ArtifactWatermark(
            offset=scan.offset,
            last_key=mark.last_key,
            totals=stamp_codex_reader({**own, CHILDREN_KEY: children}),
            truncated=mark.truncated,
            oversized=any(
                thread[USAGE_INCOMPLETE_KEY] or thread[MODEL_HISTORY_INCOMPLETE_KEY]
                for thread in threads
            ),
            caught_up=scan.caught_up and children_caught_up,
        )
        if mark != persisted_mark:
            save_watermark(session_id, path, mark)
    return _codex_reading(stored_totals(mark), source, mark)


def _fold_thread(
    path: Path, offset: int, held: Mapping[str, Any]
) -> tuple[ScanResult, dict[str, Any], list[str]]:
    """Fold one thread's rollout from ``offset`` over its held state.

    Returns the scan, the thread's new state, and the child threads its
    new rows named.
    """
    state: dict[str, Any] = {
        "latest": held.get("latest") if isinstance(held.get("latest"), dict) else None,
        "models": [str(name) for name in held.get("models", []) if str(name).strip()],
        USAGE_INCOMPLETE_KEY: bool(held.get(USAGE_INCOMPLETE_KEY)),
        MODEL_HISTORY_INCOMPLETE_KEY: bool(held.get(MODEL_HISTORY_INCOMPLETE_KEY)),
    }
    found: list[str] = []

    def mark_gap() -> None:
        state[USAGE_INCOMPLETE_KEY] = True
        state[MODEL_HISTORY_INCOMPLETE_KEY] = True

    def fold(row: Mapping[str, Any]) -> None:
        child = codex_child_thread_id(row)
        if child:
            found.append(child)
            return
        block = row.get("payload")
        if not isinstance(block, dict):
            return
        if row.get("type") == "turn_context":
            model = _text(block.get("model"))
            if model and model not in state["models"]:
                state["models"].append(model)
            return
        if block.get("type") != "token_count":
            return
        totals = _codex_totals(block)
        if totals is not None:
            state["latest"] = totals
            state[USAGE_INCOMPLETE_KEY] = False

    scan = scan_rows(
        path,
        offset,
        fold,
        record_factory=codex_record_decoder,
        on_unrecoverable=mark_gap,
    )
    state["latest"] = state["latest"] or {}
    return scan, state, found


def _fold_children(
    held: dict[str, dict[str, Any]], found: list[str], *, root: str
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Fold every known child thread, and every child those children name.

    A child forked from its parent's context repeats the parent's history,
    including the rows naming its siblings and itself, so each thread is
    folded once per call however often it is named. A child whose rollout
    cannot be found yet is kept and marked missing, so the reading says
    so and the next fold looks again.
    """
    children = dict(held)
    queue = [*held, *found]
    visited = {root}
    caught_up = True
    while queue:
        thread_id = queue.pop(0)
        if thread_id in visited:
            continue
        visited.add(thread_id)
        previous = children.get(thread_id, {})
        path = _held_rollout(previous) or _rollout(thread_id)
        if path is None:
            children[thread_id] = {**_blank_thread(previous), CHILD_MISSING_KEY: True}
            continue
        offset = normalize_count(previous.get("offset"))
        if str(path) != previous.get("path") or path.stat().st_size < offset:
            offset = 0
        scan, state, grandchildren = _fold_thread(path, offset, previous)
        children[thread_id] = {**state, "path": str(path), "offset": scan.offset}
        caught_up = caught_up and scan.caught_up
        queue.extend(grandchildren)
    return children, caught_up


def _held_children(stored: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    held = stored.get(CHILDREN_KEY)
    if not isinstance(held, dict):
        return {}
    return {
        str(tid): dict(state) for tid, state in held.items() if isinstance(state, dict)
    }


def _blank_thread(previous: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "latest": previous.get("latest") or {},
        "models": list(previous.get("models") or []),
        USAGE_INCOMPLETE_KEY: bool(previous.get(USAGE_INCOMPLETE_KEY)),
        MODEL_HISTORY_INCOMPLETE_KEY: bool(previous.get(MODEL_HISTORY_INCOMPLETE_KEY)),
    }


def _held_rollout(previous: Mapping[str, Any]) -> Optional[Path]:
    path = Path(str(previous.get("path") or ""))
    return path if previous.get("path") and path.is_file() else None


def _rollout(thread_id: str) -> Optional[Path]:
    from yoke_harness.hooks.identity_codex_runtime import codex_transcript_candidates

    candidates = codex_transcript_candidates(thread_id)
    return candidates[0] if candidates else None


def _codex_totals(block: Mapping[str, Any]) -> Optional[dict[str, int]]:
    """Convert one cumulative Codex reading into disjoint buckets.

    Codex's ``input_tokens`` contains its ``cached_input_tokens`` and its
    ``output_tokens`` contains its ``reasoning_output_tokens``, so the
    cached half is subtracted out into its own bucket while reasoning
    stays a labelled subset of the output it is already part of.
    """
    info = block.get("info")
    usage = info.get("total_token_usage") if isinstance(info, dict) else None
    if not isinstance(usage, dict):
        return None
    total_input = normalize_count(usage.get("input_tokens"))
    cached = min(normalize_count(usage.get("cached_input_tokens")), total_input)
    return {
        "input": total_input - cached,
        "cached_input": cached,
        "cache_write": normalize_count(usage.get("cache_write_input_tokens")),
        "cache_write_long": 0,
        "output": normalize_count(usage.get("output_tokens")),
        "reasoning": normalize_count(usage.get("reasoning_output_tokens")),
    }


def _codex_reading(
    stored: Mapping[str, Any], source: str, mark: ArtifactWatermark
) -> SessionUsage:
    """Present a Codex fold: each thread's newest cumulative total, summed.

    Each thread's total is attributed to the newest model that thread
    named, so a parent and a child running different models are priced
    each at its own rate.
    """
    threads = [stored, *_held_children(stored).values()]
    partial = _codex_partial_reason(threads, mark)
    totals: dict[str, dict[str, int]] = {}
    for thread in threads:
        latest = thread.get("latest")
        if isinstance(latest, dict) and latest:
            models = [
                str(name) for name in thread.get("models", []) if str(name).strip()
            ]
            _accumulate(totals, models[-1] if models else UNNAMED_MODEL, latest)
    if not totals:
        return _empty_reading(source, partial)
    reading = _reading(totals, source=source, partial=partial)
    caveat = _codex_cost_caveat(threads)
    return with_cost_caveat(reading, caveat) if caveat else reading


def _persisted_codex_reading(session_id: str, path: Path, source: str) -> SessionUsage:
    mark = load_watermark(session_id, path)
    return _codex_reading(stored_totals(mark), source, mark)


def _codex_partial_reason(
    threads: list[Mapping[str, Any]], mark: ArtifactWatermark
) -> Optional[str]:
    """Why the token counts themselves are less than the whole session.

    A lost record is deliberately not partiality by itself here, which is
    why the mark's own oversized flag is set aside before asking for the
    shared reason. Codex states its consumption cumulatively, so the
    newest statement covers every turn including the ones whose records
    could not be read: what such a loss costs is the model history, and
    the stored flags say which of the two it was.
    """
    if any(thread.get(USAGE_INCOMPLETE_KEY) for thread in threads):
        return USAGE_GAP_REASON
    if any(thread.get(CHILD_MISSING_KEY) for thread in threads):
        return CHILD_ROLLOUT_MISSING_REASON
    return partial_reason(replace(mark, oversized=False))


def _codex_cost_caveat(threads: list[Mapping[str, Any]]) -> str:
    """Why an estimate priced from those exact tokens is still uncertain."""
    if any(thread.get(MODEL_HISTORY_INCOMPLETE_KEY) for thread in threads):
        return MODEL_HISTORY_GAP_REASON
    if any(len(thread.get("models") or []) > 1 for thread in threads):
        return MIXED_MODEL_REASON
    return ""


__all__ = [
    "CHILD_ROLLOUT_MISSING_REASON",
    "MIXED_MODEL_REASON",
    "MODEL_HISTORY_GAP_REASON",
    "USAGE_GAP_REASON",
    "attest_codex_usage",
]
