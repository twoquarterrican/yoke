"""Portable diagnoses for declared and sealed baseline requests.

Only error envelopes and fixed native error phrases are evidence. Results
are static: account text and vendor payloads never leave the host.
"""

from __future__ import annotations

import json
import re

NATIVE_FAILURES = {
    "probe_quota_exhausted": (
        "the provider reports an exhausted usage quota",
        "Wait for the provider's quota window to reset or have the operator restore "
        "plan capacity, then retry the probe; preserve the existing golden.",
    ),
    "probe_auth_rejected": (
        "the provider rejected the harness credentials",
        "Sign in to the named harness in the test user's session, then retry.",
    ),
    "probe_model_rejected": (
        "the provider rejected the requested model",
        "Check the harness model selection and the account's model access, correct "
        "the rejected selection, then retry the probe.",
    ),
    "probe_transport_failed": (
        "the native request failed on a transient provider or network error",
        "Check host connectivity and provider status, then retry the probe after "
        "the service recovers; preserve the existing golden.",
    ),
    "probe_rate_limited": (
        "the provider throttled the native request",
        "Wait for the provider's request throttle to clear, then retry the probe; "
        "preserve the existing golden.",
    ),
    "cursor_workspace_trust_required": (
        "Cursor refused: Workspace Trust Required",
        "Retry the Cursor probe with `--trust --workspace /tmp`; if refused again, "
        "repair Cursor's scratch-workspace trust.",
    ),
}
_CODE_CAUSES = {
    "usage_limit_exceeded": "probe_quota_exhausted",
    "usage_limit_reached": "probe_quota_exhausted",
    "insufficient_quota": "probe_quota_exhausted",
    "quota_exceeded": "probe_quota_exhausted",
    "rate_limit": "probe_rate_limited",
    "rate_limit_error": "probe_rate_limited",
    "rate_limit_exceeded": "probe_rate_limited",
    "authentication_error": "probe_auth_rejected",
    "unauthorized": "probe_auth_rejected",
    "invalid_api_key": "probe_auth_rejected",
    "model_not_found": "probe_model_rejected",
    "invalid_model": "probe_model_rejected",
    "model_not_supported": "probe_model_rejected",
    "overloaded_error": "probe_transport_failed",
    "server_overloaded": "probe_transport_failed",
    "api_connection_error": "probe_transport_failed",
    "http_connection_failed": "probe_transport_failed",
    "stream_disconnected": "probe_transport_failed",
}
# No loose words such as 'quota', 'login' or 'model'.
_PHRASES = (
    (
        "probe_quota_exhausted",
        r"(?:you(?:'ve| have) (?:hit|reached) your (?:weekly |usage )?limit|weekly (?:usage )?limit (?:reached|exceeded)|usage limit (?:reached|exceeded)|quota (?:exhausted|exceeded))",
    ),
    (
        "probe_auth_rejected",
        r"(?:oauth (?:session expired|refresh failed)|invalid api key|401 unauthorized|authentication (?:failed|required)|expired (?:oauth |access )?token)",
    ),
    (
        "probe_model_rejected",
        r"(?:unknown model|unsupported model|invalid model|model (?:is not supported|does not exist))",
    ),
    (
        "probe_transport_failed",
        r"(?:connection (?:reset|refused|timed out)|network (?:error|unreachable)|503 service unavailable|502 bad gateway|server overloaded)",
    ),
    (
        "probe_rate_limited",
        r"(?:429 too many requests|rate limit exceeded|too many requests)",
    ),
    ("cursor_workspace_trust_required", r"workspace trust required"),
)


def _diagnose(code: object, message: str, *, plain: bool = False) -> str | None:
    for cause, pattern in _PHRASES:
        match = re.search(r"\b" + pattern + r"\b", message, re.IGNORECASE)
        if match and (not plain or match.start() == 0):
            return cause
    return _CODE_CAUSES.get(code) if isinstance(code, str) else None


def native_failure_cause(stdout: str, stderr: str) -> str | None:
    """Successful answer text cannot diagnose a failure."""
    causes = []
    for line in (stdout + "\n" + stderr).splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            text = re.sub(r"^(?:error:\s*)", "", line.strip(), flags=re.IGNORECASE)
            cause = _diagnose(None, text, plain=True)
            if cause:
                causes.append(cause)
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if not (
            kind in {"error", "turn.failed"}
            or kind == "result"
            and event.get("is_error") is True
            or kind == "assistant"
            and event.get("error")
        ):
            continue
        error = event.get("error", event)
        code = error if isinstance(error, str) else None
        messages = []
        for value in (event, error, event.get("message")):
            if not isinstance(value, dict):
                continue
            code = value.get("code", value.get("codex_error_info", code))
            if value is error and code is None:
                code = value.get("type")
            for key in ("message", "result"):
                if isinstance(value.get(key), str):
                    messages.append(value[key])
            errors = value.get("errors")
            if isinstance(errors, list):
                messages.extend(x for x in errors if isinstance(x, str))
            content = value.get("content")
            if isinstance(content, list):
                messages.extend(
                    block["text"]
                    for block in content
                    if isinstance(block, dict) and isinstance(block.get("text"), str)
                )
        cause = _diagnose(code, "\n".join(messages))
        if cause:
            causes.append(cause)
    # A final generic throttle must not erase an earlier explicit quota wall.
    return next((cause for cause in NATIVE_FAILURES if cause in causes), None)
