"""Whether an item carries a spec beyond its own title.

Single source of truth for the slack-bounded "spec is title-only"
classification used by:

- :mod:`yoke_core.domain.backlog_create_op` — every create refuses a spec
  that says nothing beyond the title, so an item is born with its agreed
  outcome.
- ``POST /v1/items`` — the REST create applies the same refusal.
- :mod:`yoke_core.domain.frontier_compute` — an item left title-only by an
  older release waits on the frontier labelled "Needs a spec" instead of
  being handed to a session with nothing to work from.
- :mod:`yoke_core.engines.doctor_hc_meta_backlog` — reports those leftovers.

Every consumer reads the one classification here so they cannot disagree.
"""

from __future__ import annotations

from typing import Mapping, Optional


NEEDS_SPEC_LABEL = "Needs a spec"
"""Name every surface shows for an item whose spec is title-only."""

SPEC_REQUIRED_CODE = "spec_required"
"""Refusal code for a create that supplies no spec beyond the title."""


def _coerce_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    return str(value)


def spec_is_title_only(title: str, spec: Optional[str]) -> bool:
    """Return True when *spec* is blank or only repeats the title.

    The comparison is on content, not length: ``# Title`` (any heading
    level, any surrounding whitespace) is title-only, while a short real
    outcome under a long title is a spec.
    """
    text = _coerce_text(spec).strip()
    core = text.lstrip("#").strip()
    return not core or core == _coerce_text(title).strip()


def missing_spec_refusal(title: str, spec: Optional[str]) -> Optional[str]:
    """Return the create refusal for a title-only spec, or None when it has one."""
    if not spec_is_title_only(title, spec):
        return None
    return (
        f"{SPEC_REQUIRED_CODE}: an item is created together with its spec. "
        "Write the agreed outcome (problem, intended result, how to tell it is "
        "done) to a file and pass --spec-file PATH, or pipe it with --stdin; "
        "refinement adds detail later. A spec that only repeats the title "
        "does not count."
    )


def item_needs_spec(item_row: Mapping[str, object]) -> bool:
    """Return True when the row's spec/body is at most title-only.

    Accepts either a database row or a plain mapping. Reads ``spec`` first
    (the structured field that backs the virtual body) and falls back to a
    ``body`` key when callers pass a pre-rendered row.
    """
    title = _coerce_text(_safe_get(item_row, "title"))
    spec = _coerce_text(_safe_get(item_row, "spec"))
    return spec_is_title_only(
        title, spec if spec else _coerce_text(_safe_get(item_row, "body"))
    )


def needs_spec_reason(public_ref: str) -> str:
    """Frontier and doctor wording for a title-only item, with its repair."""
    return (
        f"{NEEDS_SPEC_LABEL}: {public_ref} was saved with only its title, so no "
        "session can start it. Claim it and write its spec with "
        f"`yoke items structured-field replace {public_ref} --field spec --stdin`, "
        f'or cancel it with `yoke items cancel {public_ref} --reason "<why>"`.'
    )


def _safe_get(item_row: Mapping[str, object], key: str) -> Optional[object]:
    if hasattr(item_row, "get"):
        return item_row.get(key)
    try:
        return item_row[key]
    except (KeyError, IndexError):
        return None


__all__ = [
    "NEEDS_SPEC_LABEL",
    "SPEC_REQUIRED_CODE",
    "item_needs_spec",
    "missing_spec_refusal",
    "needs_spec_reason",
    "spec_is_title_only",
]
