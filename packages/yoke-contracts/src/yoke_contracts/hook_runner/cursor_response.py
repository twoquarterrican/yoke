"""Cursor allow-response requirements shared by every hook exit path."""

from __future__ import annotations

import json

CURSOR_LIFECYCLE_EVENTS = frozenset({"Stop", "SessionEnd"})
CURSOR_PERMISSION_EVENTS = frozenset({"PreToolUse", "apply_patch"})
CURSOR_CONTEXT_EVENTS = frozenset({"SessionStart", "PostToolUse"})


def cursor_allow_stdout(
    event_name: str,
    preserved_stdout: str = "",
) -> str:
    """Preserve decisions and render valid allow replies on gated events.

    Empty stdout is not an allow verdict for Cursor permission hooks. Local
    advisories use the shared envelope; convert them only on events whose
    native contract accepts context, never as a permission-hook response.
    """
    if preserved_stdout:
        try:
            payload = json.loads(preserved_stdout)
        except (ValueError, TypeError):
            return preserved_stdout
        if isinstance(payload, dict):
            if event_name in CURSOR_PERMISSION_EVENTS and set(payload) == {
                "additional_context"
            }:
                return json.dumps({"permission": "allow"})
            inner = payload.get("hookSpecificOutput")
            if isinstance(inner, dict) and "permissionDecision" not in inner:
                body = inner.get("additionalContext")
                if isinstance(body, str):
                    if event_name in CURSOR_CONTEXT_EVENTS:
                        return json.dumps({"additional_context": body})
                    if event_name in CURSOR_PERMISSION_EVENTS:
                        return json.dumps({"permission": "allow"})
        return preserved_stdout
    if event_name in CURSOR_PERMISSION_EVENTS:
        return json.dumps({"permission": "allow"})
    return "{}" if event_name in CURSOR_LIFECYCLE_EVENTS else ""


__all__ = [
    "CURSOR_LIFECYCLE_EVENTS",
    "CURSOR_PERMISSION_EVENTS",
    "CURSOR_CONTEXT_EVENTS",
    "cursor_allow_stdout",
]
