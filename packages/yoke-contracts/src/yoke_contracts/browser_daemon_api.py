"""The browser daemon's HTTP surface, named once for every client of it.

Two Python clients talk to the same daemon — ``yoke_core.domain``'s, which
runs authored QA cases, and ``yoke_harness``'s, which an exploratory agent
drives one step per command. Neither can import the other, so the paths they
share are stated here rather than spelled twice.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

#: Run one step against a page the caller names.
EXEC_STEP_PATH = "/api/exec/step"

#: Open the page a run owns, or return a named page that is still open.
EXEC_PAGE_PATH = "/api/exec/page"

#: Release a page. A page already gone is already released.
EXEC_PAGE_CLOSE_PATH = "/api/exec/page/close"


DEFAULT_DAEMON_REQUEST_TIMEOUT_SECONDS = 30
STEP_RESPONSE_HEADROOM_SECONDS = 15


def step_request_timeout_seconds(step: Mapping[str, Any]) -> float:
    """Give a finite positive action budget room to return its own verdict."""
    declared_ms = step.get("timeout_ms")
    if (
        isinstance(declared_ms, bool)
        or not isinstance(declared_ms, (int, float))
        or declared_ms <= 0
    ):
        return DEFAULT_DAEMON_REQUEST_TIMEOUT_SECONDS
    try:
        seconds = declared_ms / 1000
    except OverflowError:
        return DEFAULT_DAEMON_REQUEST_TIMEOUT_SECONDS
    if not math.isfinite(seconds):
        return DEFAULT_DAEMON_REQUEST_TIMEOUT_SECONDS
    return max(
        DEFAULT_DAEMON_REQUEST_TIMEOUT_SECONDS,
        seconds + STEP_RESPONSE_HEADROOM_SECONDS,
    )


__all__ = [
    "DEFAULT_DAEMON_REQUEST_TIMEOUT_SECONDS",
    "step_request_timeout_seconds",
    "EXEC_PAGE_CLOSE_PATH",
    "EXEC_PAGE_PATH",
    "EXEC_STEP_PATH",
]
