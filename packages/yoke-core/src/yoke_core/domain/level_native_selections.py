"""Expand model/effort rows only into selectors observed on a native surface."""

from dataclasses import dataclass
from yoke_contracts.model_level_resolution import normalized_effort
from yoke_contracts.model_reference import lookup_model_reference
from yoke_contracts.session_control.model_selection import (
    LaunchModelSelection,
    LaunchModelSelectionError,
    validate_launch_model_selection,
)
from yoke_contracts.session_control.native_model_parsers import cursor_token_effort


@dataclass(frozen=True)
class NativeLevelSelection:
    surface: str
    model: str
    reasoning_effort: str
    context_window_tokens: int | None = None


def native_selections(entry, *, surface, reading, records):
    """Return every offered selector at the minimum effort, plus refusal detail."""
    reading = reading or {}
    if reading.get("status") == "unsupported":
        return (
            (),
            f"native_models_unsupported: {reading.get('reason') or 'no native listing adapter'}; ask the control-plane operator to provide this surface's listing adapter, or choose a surface with observed models",
        )
    if reading.get("status") not in {"ok", "stale"}:
        return (
            (),
            f"native_models_{reading.get('status', 'unknown')}: {reading.get('reason') or 'no native listing observed'}; refresh with yoke relay probe-models --surface {surface}",
        )
    required = lookup_model_reference(entry.model, records).record
    if required is None:
        return (
            (),
            f"model_catalog_missing: {entry.model}; publish researched model facts with yoke models publish",
        )
    if entry.min_effort not in {
        normalized_effort(value) for value in required.reasoning_efforts
    }:
        return (
            (),
            f"model_effort_unpublished: {entry.model} at {entry.min_effort}; publish researched effort facts with yoke models publish",
        )
    matched = []
    for native in reading.get("models", ()):
        token = str(native.get("model") or "")
        record = lookup_model_reference(token, records).record
        if record is None or record.model_id != required.model_id:
            continue
        efforts = native.get("reasoning_efforts") or (cursor_token_effort(token),)
        effort = next(
            (
                str(value)
                for value in efforts
                if normalized_effort(value) == entry.min_effort
            ),
            None,
        )
        if effort is None:
            continue
        try:
            selected = validate_launch_model_selection(
                surface, LaunchModelSelection(token, effort, None)
            )
        except LaunchModelSelectionError:
            continue
        matched.append(
            NativeLevelSelection(surface, selected.model, selected.reasoning_effort)
        )
    return (
        tuple(matched),
        None
        if matched
        else f"native_model_effort_unavailable: {entry.model} at {entry.min_effort} is not offered on {surface}; refresh the native listing or choose another level",
    )
