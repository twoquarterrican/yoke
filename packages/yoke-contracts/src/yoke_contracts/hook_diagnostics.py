"""Human diagnostic labels shared by Git and harness hooks.

Call only for human prose, never wire envelopes, delivery frames or identity
values. Successful checks emit no diagnostic; required context has its own
composer and is never filtered by this formatter.
"""

from __future__ import annotations


def format_hook_diagnostic(hook: str, text: str) -> str:
    """Attribute one human diagnostic without changing its recovery text."""
    if not text or not text.strip():
        return ""
    if text.startswith("yoke ("):
        return text
    return f"yoke ({hook}): {text}"
