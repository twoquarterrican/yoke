"""Action-safe, bounded browser daemon failure diagnostics."""

import json

from yoke_cli.transport.bounded_json_http import (
    BoundedJsonHttpDeadlineError,
    BoundedJsonHttpStatusError,
    safe_diagnostic_text,
)


def daemon_failure_message(error: Exception, *, token: str) -> str:
    """Keep the scrubbed daemon reason without replaying an uncertain action."""
    detail = str(error)
    reason = "browser_daemon_request_failed"
    if isinstance(error, BoundedJsonHttpStatusError):
        reason = "browser_daemon_http_error"
        if error.payload is not None:
            detail += ": " + json.dumps(error.payload, ensure_ascii=True)
    elif isinstance(error, BoundedJsonHttpDeadlineError):
        reason = "browser_daemon_response_timeout"
    detail = safe_diagnostic_text(detail, sensitive_values=(token,))
    return (
        f"{reason}: daemon request failed: {detail}. "
        "The action may have completed; inspect the existing page and retained "
        "evidence before recovery. Do not replay a submit blindly. "
        "Check `yoke qa browser status` for daemon health."
    )
