"""How a receipt past its message's expiry reads before anything persists it.

A session or person receipt that is still open when its message expires is
expired, whether or not a row says so yet. Reads apply that rule
themselves -- the list filters and the projections below -- so a read never
writes. Persisting the state is the relay claim cycle's set-based sweep
(:func:`yoke_core.domain.session_message_delivery.expire_due_recipients`),
which converges the stored rows to exactly what these reads already show.

Steering rows are not covered here: their table has no ``expired`` state,
so readers judge a steering row's staleness from the message instead.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from yoke_contracts.timestamps import parse_instant


OPEN_SESSION_STATES: tuple[str, ...] = ("pending", "injected")
_LEASE_FIELDS = (
    "injection_lease_id",
    "injection_leased_at",
    "injection_lease_expires_at",
)


def session_state_sql(
    marker: str, states: tuple[str, ...], now: Any
) -> tuple[str, list[Any]]:
    """Match session receipts (alias ``r``) whose effective state is in ``states``."""

    def slots(values: tuple[str, ...]) -> str:
        return ",".join(marker for _ in values)

    branches: list[str] = []
    params: list[Any] = []
    still_open = tuple(state for state in states if state in OPEN_SESSION_STATES)
    if still_open:
        branches.append(f"(r.state IN ({slots(still_open)}) AND m.expires_at>{marker})")
        params.extend([*still_open, now])
    if "expired" in states:
        branches.append(
            f"(r.state IN ({slots(OPEN_SESSION_STATES)}) AND m.expires_at<={marker})"
        )
        params.extend([*OPEN_SESSION_STATES, now])
    settled = tuple(state for state in states if state not in OPEN_SESSION_STATES)
    if settled:
        branches.append(f"r.state IN ({slots(settled)})")
        params.extend(settled)
    return "(" + " OR ".join(branches) + ")", params


def actor_state_sql(marker: str, state: str, now: Any) -> tuple[str, list[Any]]:
    """Match person receipts (alias ``ar``) whose effective state is ``state``."""
    if state == "pending":
        return (
            f"(ar.state='pending' AND m.cancelled_at IS NULL "
            f"AND m.expires_at>{marker})",
            [now],
        )
    if state == "expired":
        return (
            "(ar.state='expired' OR (ar.state='pending' AND "
            f"(m.cancelled_at IS NOT NULL OR m.expires_at<={marker})))",
            [now],
        )
    return f"ar.state={marker}", [state]


def project_due_receipts(message: dict[str, Any], *, now: datetime) -> None:
    """Read every open receipt on a message past its expiry as expired.

    ``message`` carries its stored ``expires_at``/``cancelled_at`` and its
    ``recipients``/``actor_recipients`` lists; the receipts change in place.
    ``expired_at`` reads as the instant the receipt became due.
    """
    expires_at = message.get("expires_at")
    due = expires_at is not None and parse_instant(expires_at) <= now
    cancelled_at = message.get("cancelled_at")
    if due:
        for receipt in message.get("recipients") or []:
            if receipt.get("state") in OPEN_SESSION_STATES:
                receipt["state"] = "expired"
                receipt["expired_at"] = expires_at
                for key in _LEASE_FIELDS:
                    if key in receipt:
                        receipt[key] = None
    if due or cancelled_at is not None:
        for receipt in message.get("actor_recipients") or []:
            if receipt.get("state") == "pending":
                receipt["state"] = "expired"
                receipt["expired_at"] = cancelled_at if not due else expires_at


__all__ = [
    "OPEN_SESSION_STATES",
    "actor_state_sql",
    "project_due_receipts",
    "session_state_sql",
]
