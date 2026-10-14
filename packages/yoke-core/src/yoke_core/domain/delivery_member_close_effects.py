"""A closed member's post-commit effects, never inside a held transaction.

A run's close-out spends most of its time outside the database: GitHub
sync, retiring each member's lanes, and sweeping each checkout's merged
lanes. No transaction may stay open across that work. The server ends a
session left idle in a transaction past its bound, and every later write on
that connection then fails with ``the connection is closed``.

So the effects never borrow the caller's connection. Each database step
opens its own connection, commits, and closes it before any file-system or
network work runs, and a connection that drops mid-step is reopened once:
every step is idempotent. A lost connection therefore costs at most the one
member whose step it carried, never the members after it.
"""

from __future__ import annotations

import io
import sys
from typing import Any, Callable

from yoke_contracts.api.function_call import TargetRef
from yoke_core.api.service_client_structured_api_adapter import call_dispatcher
from yoke_core.domain import db_backend
from yoke_core.domain.db_helpers import connect
from yoke_core.domain.function_connection_loss import retry_dropped_connection
from yoke_core.domain.standalone_item_merge_evidence import CLOSED_OUT_STATUS


def _in_short_transaction(step: Callable[[Any], None]) -> None:
    """Run *step* on a fresh connection and commit; reopen once if it drops."""

    def _once() -> None:
        conn = connect()
        try:
            step(conn)
            conn.commit()
        finally:
            conn.close()

    retry_dropped_connection(_once)


def _closed_item(public_ref: str) -> tuple[dict[str, Any], str]:
    """The closed member as terminal lane cleanup reads it, or why it could not.

    The same ``items.detail.get`` read a standalone close-out retires lanes
    from: the project names this machine's checkout and the target branch,
    and the lane rows name what to retire.
    """
    try:
        response = call_dispatcher(
            function_id="items.detail.get",
            target=TargetRef(kind="item", public_ref=public_ref),
            payload={},
        )
    except Exception as exc:  # noqa: BLE001 - reported as a cleanup warning
        return {}, str(exc) or exc.__class__.__name__
    if not response.success:
        error = response.error
        return {}, error.message if error is not None else "item read refused"
    return (response.result or {}).get("item") or {}, ""


def _retire_closed_member_lanes(public_ref: str) -> list[str]:
    """Retire the closed member's own lanes; return what was preserved."""
    from yoke_core.domain.terminal_lane_cleanup import record_terminal_lane_close_out

    item, refusal = _closed_item(public_ref)
    if refusal:
        return [
            f"{public_ref}: terminal lane cleanup preserved: the item could not "
            f"be read ({refusal})"
        ]
    envelope: dict[str, Any] = {"warnings": []}
    record_terminal_lane_close_out(
        item, envelope, target_status=CLOSED_OUT_STATUS, machine_sweep=False
    )
    return list(envelope["warnings"])


def sweep_closed_member_checkouts(public_refs: list[str]) -> list[str]:
    """Sweep each distinct checkout of these closed members once.

    A member close-out retires only that member's lanes. The run calls this
    after every member has closed.
    """
    from yoke_core.domain.terminal_lane_cleanup import (
        item_lane_checkout,
        sweep_managed_lanes,
    )

    def _emit(message: str, **_kw: Any) -> None:
        print(message, file=sys.stderr, flush=True)

    seen: set[tuple[str, str]] = set()
    warnings: list[str] = []
    for public_ref in public_refs:
        item, refusal = _closed_item(public_ref)
        if refusal or not item:
            continue
        resolved = item_lane_checkout(item)
        if resolved is None:
            continue
        root, target = resolved
        key = (str(root), target)
        if key in seen:
            continue
        seen.add(key)
        found, _payload = sweep_managed_lanes(repo_root=root, target=target, emit=_emit)
        warnings.extend(found)
    return warnings


def run_closed_member_effects(
    *,
    item_id: int,
    public_ref: str,
    receipt: Any = None,
) -> str:
    """Run a closed member's post-commit effects; name any that failed.

    Every step is idempotent, so a replay over a member whose effects
    already ran repeats nothing harmful. ``receipt`` is the status write's
    own effect receipt, held only by the pass that committed the close.
    Lane cleanup is best-effort: what it preserved is printed with the
    recovery that retires it, and never fails the close.
    Returns ``""`` when every effect finished.
    """
    from yoke_core.domain.backlog_update_effects import (
        run_post_commit_update_effects,
    )
    from yoke_core.domain.standalone_item_merge import sync_item_to_github
    from yoke_core.domain.worktree_capacity import DOCTOR_RETIRE_RECIPE

    try:
        if receipt is not None:
            _in_short_transaction(
                lambda conn: run_post_commit_update_effects(
                    conn, receipt=receipt, out=io.StringIO()
                )
            )
        github_error = sync_item_to_github(int(item_id))
        lane_warnings = _retire_closed_member_lanes(public_ref)
        _in_short_transaction(
            lambda conn: _end_previous_claim_holders_if_empty(conn, item_id=item_id)
        )
    except Exception as exc:  # noqa: BLE001 - reported; the close stays committed
        return str(exc) or exc.__class__.__name__
    if github_error:
        print(f"{public_ref}: GitHub sync skipped: {github_error}", flush=True)
    for warning in lane_warnings:
        print(f"Lane cleanup warning: {warning}", flush=True)
    if lane_warnings:
        print(
            f"{public_ref}: once each preserved lane is resolved, retire it "
            f"with `{DOCTOR_RETIRE_RECIPE}` on the machine holding it.",
            flush=True,
        )
    if receipt is not None:
        print(
            f"{public_ref}: post-deploy obligations satisfied; closed without a wake."
        )
    return ""


def _end_previous_claim_holders_if_empty(conn: Any, *, item_id: int) -> None:
    """End any previous holding sessions released by the transition if now empty."""
    from yoke_core.domain.sessions_render_end_if_empty import end_session_if_empty
    from yoke_core.domain.work_claim_targets import scope_int_sql

    marker = "%s" if db_backend.connection_is_postgres(conn) else "?"
    item_scope = scope_int_sql(conn, "scope", "item_id")
    epic_scope = scope_int_sql(conn, "scope", "epic_id")
    release_intent = f"item-terminal:{CLOSED_OUT_STATUS}"

    rows = conn.execute(
        "SELECT DISTINCT session_id FROM work_claims "
        f"WHERE release_reason_intent={marker} AND "
        f"((target_kind='item' AND {item_scope}={marker}) OR "
        f"(target_kind='epic_task' AND {epic_scope}={marker}))",
        (release_intent, int(item_id), int(item_id)),
    ).fetchall()

    session_ids = [
        str(row["session_id"] if hasattr(row, "keys") else row[0])
        for row in rows
        if row and (row["session_id"] if hasattr(row, "keys") else row[0])
    ]

    for session_id in sorted(set(session_ids)):
        try:
            end_session_if_empty(
                conn,
                session_id,
                triggered_by="delivery-satisfied-closeout",
            )
        except Exception:  # noqa: BLE001 - best-effort session cleanup
            pass


__all__ = ["run_closed_member_effects", "sweep_closed_member_checkouts"]
