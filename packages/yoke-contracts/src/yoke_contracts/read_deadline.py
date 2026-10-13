"""One read budget carried through handler code and blocking transports."""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar

FUNCTION_RESPONSE_TIMEOUT_SECONDS = 30.0
READ_RESPONSE_RESERVE_SECONDS = 5.0
_deadline: ContextVar[float | None] = ContextVar("function_read_deadline", default=None)


class ReadDeadlineExceeded(BaseException):
    """Unwind expired reads through best-effort exception handlers."""


def remaining_seconds(timeout: float) -> float:
    deadline = _deadline.get()
    if deadline is None:
        return timeout
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ReadDeadlineExceeded("read_deadline_exceeded")
    return min(timeout, remaining)


def active() -> bool:
    return _deadline.get() is not None


@contextmanager
def read_budget(seconds: float):
    previous = _deadline.get()
    deadline = time.monotonic() + seconds
    token = _deadline.set(min(previous, deadline) if previous is not None else deadline)
    try:
        yield
        remaining_seconds(seconds)
    finally:
        _deadline.reset(token)


def bound_deadline(deadline: float) -> float:
    previous = _deadline.get()
    if previous is None:
        return deadline
    remaining_seconds(FUNCTION_RESPONSE_TIMEOUT_SECONDS)
    return min(previous, deadline)
