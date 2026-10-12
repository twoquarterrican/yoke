"""Converge and validate a restored database inside its copy admission."""

from __future__ import annotations

from typing import Any, Callable

from yoke_core.domain.migration_restore_point import named_restore_point
from yoke_core.domain import postgres_cluster


def validate_copy(
    validator: Callable | None, conn: Any, dsn: str, boundary: str
) -> Any:
    """Turn both a refused result and an exception into a named, redacted failure.

    A validator's NotApplicable passes through unchanged for the verdict to name.
    """
    from yoke_core.domain.migration_fleet_preflight import NotApplicable

    if validator is None:
        return None
    try:
        detail = validator(conn, dsn)
    except BaseException as exc:  # noqa: BLE001 -- copy failure, never release proof
        detail = f"{type(exc).__name__}: {exc}"
    if detail is None or isinstance(detail, NotApplicable):
        return detail
    from yoke_core.domain.migration_fleet_declared_plan import redact_dsn

    return redact_dsn(
        f"rehearsal_{boundary}_failed: {detail}; repair the candidate or copied "
        "release declaration and rerun fleet preflight; no release receipt was earned",
        dsn,
    )


def _split(outcome: Any, not_applicable: list) -> str | None:
    """Collect a NotApplicable outcome; return only a failure detail."""
    if outcome is None or isinstance(outcome, str):
        return outcome
    not_applicable.append(outcome)
    return None


def converge_copy(spec, database, copy_name, dump, plan):
    from yoke_core.domain.migration_fleet_preflight import Verdict
    from yoke_core.domain import db_backend
    from yoke_core.domain.migration_fleet_applied_invariants import (
        AppliedInvariantReport,
        applied_shipped_names,
        verify_applied_history_invariants,
    )

    copy_dsn = postgres_cluster.dsn(spec, copy_name)
    # Boot-shaped rows (name + index). connect_psycopg stays tuple-only.
    conn = db_backend._open_native_postgres(copy_dsn)
    try:
        pending = plan.pending_names(conn, plan.history)
        not_applicable: list = []
        failure = _split(
            validate_copy(plan.pre_converge_validator, conn, copy_dsn, "pre_boot"),
            not_applicable,
        )
        if failure is not None:
            conn.rollback()
            return Verdict(database, False, failure, pending)
        with named_restore_point(dump):
            try:
                plan.converge(conn, copy_dsn)
            except BaseException as exc:  # noqa: BLE001 — a verdict, not a crash
                conn.rollback()
                return Verdict(database, False, str(exc).strip(), pending)
        applied = applied_shipped_names(plan.history, plan.pending_names, conn)
        report = (
            AppliedInvariantReport()
            if plan.load_module is None
            else verify_applied_history_invariants(
                conn,
                applied,
                history=plan.history,
                load_module=plan.load_module,
                redact=copy_dsn,
            )
        )
        failure = report.failure
        if failure is None and plan.post_converge_validator is not None:
            failure = _split(
                validate_copy(
                    plan.post_converge_validator, conn, copy_dsn, "post_boot"
                ),
                not_applicable,
            )
        if failure is not None:
            conn.rollback()
        else:
            conn.commit()
        return Verdict(
            database,
            failure is None,
            plan.success_detail if failure is None else failure,
            pending,
            applied,
            skipped_invariants=report.skipped,
            not_applicable=tuple(not_applicable),
        )
    finally:
        conn.close()
