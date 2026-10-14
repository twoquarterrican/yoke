"""Operation-wide deadline accounting for retried GitHub REST calls."""

from __future__ import annotations

import math
from collections.abc import Callable

from yoke_contracts.read_deadline import active as read_budget_active
from yoke_contracts.read_deadline import remaining_seconds
from yoke_core.domain import github_response_safety
from yoke_core.domain.gh_rest_transport_errors import RestNetworkError


class GitHubRestOperationDeadlineError(TimeoutError):
    """A GitHub REST request exhausted its whole-operation deadline."""


def operation_deadline_after(unbounded_seconds: float) -> float:
    """Return the absolute deadline for one retried GitHub operation.

    Inside a bounded function read the shared read budget is the only
    limit, so retries and log reads fit the read that called them;
    *unbounded_seconds* applies only outside one.
    """

    seconds = remaining_seconds(math.inf) if read_budget_active() else unbounded_seconds
    return github_response_safety.deadline_after(seconds)


def deadline_cut_error(
    exc: GitHubRestOperationDeadlineError,
    last_error: Exception | None,
) -> RestNetworkError:
    """Report a deadline cut together with the real error it stopped retrying."""

    if last_error is None:
        return RestNetworkError(str(exc))
    return RestNetworkError(f"{exc}; last GitHub error: {last_error}")


def require_remaining(deadline: float, *, clock: Callable[[], float]) -> float:
    """Return positive operation time remaining or raise a typed timeout."""

    remaining = deadline - clock()
    if not math.isfinite(remaining) or remaining <= 0:
        raise GitHubRestOperationDeadlineError(
            "GitHub REST operation exceeded the time limit"
        )
    return remaining


def wait_before_retry(
    deadline: float,
    wait_seconds: float,
    *,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> None:
    """Sleep only when the complete backoff fits inside the operation."""

    remaining = require_remaining(deadline, clock=clock)
    try:
        wait = float(wait_seconds)
    except (TypeError, ValueError, OverflowError) as exc:
        raise GitHubRestOperationDeadlineError(
            "GitHub REST retry delay is invalid"
        ) from exc
    if not math.isfinite(wait) or wait < 0:
        raise GitHubRestOperationDeadlineError("GitHub REST retry delay is invalid")
    if wait >= remaining:
        raise GitHubRestOperationDeadlineError(
            "GitHub REST operation exceeded the time limit"
        )
    sleeper(wait)
    require_remaining(deadline, clock=clock)


__all__ = [
    "GitHubRestOperationDeadlineError",
    "deadline_cut_error",
    "operation_deadline_after",
    "require_remaining",
    "wait_before_retry",
]
