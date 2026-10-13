"""Bound side-effect-free registered handlers before transport abandonment."""

from __future__ import annotations

from yoke_contracts.api.function_call import FunctionError, HandlerOutcome
from yoke_contracts.read_deadline import (
    FUNCTION_RESPONSE_TIMEOUT_SECONDS,
    READ_RESPONSE_RESERVE_SECONDS,
    ReadDeadlineExceeded,
    read_budget,
    remaining_seconds,
)
from yoke_core.domain.handler_execution_context import invoke_resolved_handler
from yoke_core.domain.python_execution_deadline import native_call, run_bounded


def driver_call(method, *args, **kwargs):
    try:
        return native_call(method, *args, **kwargs)
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == "57014":
            raise ReadDeadlineExceeded("read_deadline_exceeded") from exc
        raise


def invoke_handler(entry, request):
    if set(entry.side_effects) - {"event_emit"}:
        return invoke_resolved_handler(entry.handler, request)
    seconds = FUNCTION_RESPONSE_TIMEOUT_SECONDS - READ_RESPONSE_RESERVE_SECONDS
    recovery = (
        "Retry a narrower read: name a project or section, or use --limit and "
        "--offset. Pickers use summary rows; request --full only for needed detail."
    )
    try:
        with read_budget(seconds):
            return run_bounded(
                invoke_resolved_handler,
                entry.handler,
                request,
                check=lambda: remaining_seconds(seconds),
            )
    except ReadDeadlineExceeded:
        return HandlerOutcome(
            primary_success=False,
            error=FunctionError(
                code="read_deadline_exceeded",
                message=f"{entry.function_id} exceeded its {seconds:g}s server read deadline. {recovery}",
                recovery_hint=recovery,
            ),
        )
