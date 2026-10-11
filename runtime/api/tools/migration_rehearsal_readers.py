"""Read restored rows through product surfaces after boot convergence."""

from __future__ import annotations

from typing import Any, Callable

from yoke_contracts.api.function_call import FunctionCallRequest
from yoke_core.domain import db_backend
from yoke_core.domain.handlers import (
    frontier_list,
    items_listing,
    orchestration,
    reads,
    sessions_list,
)
from yoke_core.domain.session_launch_history_page import read_launch_page
from yoke_core.domain.session_launch_projection import public_launch_record
from yoke_core.domain.session_launch_store import get_launch
from yoke_core.domain.session_message_attempt_reads import message_attempt_evidence


def checked(function: str, handler: Callable, payload=None, target=None) -> dict:
    """A handler refusal fails proof, including a caught decode error."""
    outcome = handler(
        FunctionCallRequest(
            function=function,
            actor={"session_id": "migration-rehearsal"},
            target=target or {"kind": "global"},
            payload=payload or {},
        )
    )
    if not outcome.primary_success or outcome.error is not None:
        error = outcome.error
        raise RuntimeError(
            f"{function}: {error.code}: {error.message}"
            if error
            else f"{function}: unsuccessful outcome"
        )
    return outcome.result_payload


def verify_migrated_readers(conn: Any, copy_dsn: str) -> str | None:
    """Exercise every copied record beyond the newest-N list window."""
    operation = "sessions.list"
    try:
        with db_backend.bound_pg_dsn(copy_dsn):
            session_ids = conn.execute(
                "SELECT session_id FROM harness_sessions ORDER BY session_id"
            ).fetchall()
            conn.rollback()
            checked(operation, sessions_list.handle_sessions_list)
            for row in session_ids:
                checked(
                    operation,
                    sessions_list.handle_sessions_list,
                    {"session_id": row[0]},
                )
            operation = "frontier.list"
            checked(operation, frontier_list.handle_frontier_list)
            operation = "board.data.get"
            checked(operation, orchestration.handle_board_data_get)
            projects = conn.execute(
                "SELECT id,slug FROM projects ORDER BY id"
            ).fetchall()
            for project_id, slug in projects:
                operation = f"session_control.launch.list project={slug}"
                cursor = None
                while True:
                    page = read_launch_page(conn, project_id=project_id, cursor=cursor)
                    cursor = page["next_cursor"]
                    if cursor is None:
                        break
                operation = f"items.list.run project={slug}"
                checked(
                    "items.list.run", items_listing.handle_items_list, {"project": slug}
                )
            for row in conn.execute(
                "SELECT launch_id FROM session_launches ORDER BY launch_id"
            ).fetchall():
                operation = f"session_control.launch.get launch={row[0]}"
                public_launch_record(get_launch(conn, str(row[0])))
            for row in conn.execute(
                "SELECT DISTINCT message_id FROM session_message_attempts ORDER BY message_id"
            ).fetchall():
                operation = f"messages.get attempts message={row[0]}"
                message_attempt_evidence(conn, str(row[0]))
            item_ids = conn.execute("SELECT id FROM items ORDER BY id").fetchall()
            conn.rollback()
            for row in item_ids:
                operation = f"items.get.run item={row[0]}"
                checked(
                    "items.get.run",
                    reads.handle_items_get,
                    target={"kind": "item", "item_id": row[0]},
                )
    except BaseException as exc:  # noqa: BLE001 -- copy verdict
        from yoke_core.domain.migration_fleet_declared_plan import redact_dsn

        return redact_dsn(f"{operation}: {type(exc).__name__}: {exc}", copy_dsn)
    print(
        "READERS: sessions, frontier, board, launches, message attempts and items passed",
        flush=True,
    )
    return None
