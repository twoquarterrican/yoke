"""Durable operator repair attempts in the existing migration audit owner."""

from __future__ import annotations

import json

from yoke_core.domain.db_helpers import instant_parameter, utc_now


def begin(conn, *, plan, actor_id: int, sql_hash: str, review_hash: str) -> int:
    now = instant_parameter(conn, utc_now())
    row = conn.execute(
        "INSERT INTO public.migration_audit (migration_name, description, tables_declared, "
        "expected_deltas, pre_row_counts, backup_path, state, exception_reason, "
        "source_fingerprint, baseline_verify_result, actor_id, started_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (
            "operator_data_repair",
            plan.reason,
            json.dumps([plan.table]),
            json.dumps({plan.table: len(plan.after) - len(plan.before)}),
            json.dumps({plan.table: len(plan.before)}),
            "",
            "planned",
            "Reviewed exact row repair; transactional before/after guards and durable row images replace a database dump.",
            sql_hash,
            json.dumps(
                {
                    "review_sha256": review_hash,
                    "expected_before": plan.before,
                    "expected_after": plan.after,
                }
            ),
            str(actor_id),
            now,
        ),
    ).fetchone()
    conn.commit()
    return int(row[0])


def finish(
    conn,
    audit_id: int,
    *,
    state: str,
    before: list,
    after: list,
    reason: str | None = None,
) -> None:
    updated = conn.execute(
        "UPDATE public.migration_audit SET state=%s, author_verify_result=%s, "
        "failure_reason=%s, completed_at=%s WHERE id=%s",
        (
            state,
            json.dumps({"observed_before": before, "observed_after": after}),
            reason,
            instant_parameter(conn, utc_now()),
            audit_id,
        ),
    ).rowcount
    if updated != 1:
        raise RuntimeError(
            "operator repair audit row disappeared; reconcile its durable outcome before retrying"
        )
