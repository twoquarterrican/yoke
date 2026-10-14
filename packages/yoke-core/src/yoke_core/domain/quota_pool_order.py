"""Universe-wide consumption order of Cursor's two monthly quota pools.

An absent ``universe_settings`` row reads :data:`DEFAULT_CURSOR_QUOTA_ORDER`.
A stored row freezes the order at write time. Delete that row with a reviewed
``yoke operator data-repair`` to follow the shipped order again.
"""

from yoke_contracts.session_control.plan_limits import (
    CURSOR_MODELS_SCOPE,
    CURSOR_OTHER_MODELS_SCOPE,
    cursor_scope_for_model,
)
from yoke_contracts.timestamps import utc_now
from yoke_core.domain import json_helper
from yoke_core.domain.db_helpers import instant_parameter
from yoke_core.domain.machine_registry import marker

KEY = "cursor_quota_order"
DEFAULT_CURSOR_QUOTA_ORDER = (CURSOR_MODELS_SCOPE, CURSOR_OTHER_MODELS_SCOPE)


class QuotaPoolOrderError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def validate_cursor_quota_order(pools):
    if (
        not isinstance(pools, list)
        or len(pools) != 2
        or not all(isinstance(pool, str) for pool in pools)
        or set(pools) != set(DEFAULT_CURSOR_QUOTA_ORDER)
    ):
        raise QuotaPoolOrderError(
            "cursor_quota_order_invalid",
            "Use exactly Cursor Models and Other Models, once each. Recovery: yoke universe cursor-quota-order set --pool 'Cursor Models' --pool 'Other Models'.",
        )
    return tuple(pools)


def read_pool_order(conn):
    row = conn.execute(
        f"SELECT value FROM universe_settings WHERE key = {marker(conn)}", (KEY,)
    ).fetchone()
    if row is None:
        return DEFAULT_CURSOR_QUOTA_ORDER
    try:
        return validate_cursor_quota_order(json_helper.loads_text(str(row[0])))
    except (TypeError, ValueError) as exc:
        if isinstance(exc, QuotaPoolOrderError):
            raise
        raise QuotaPoolOrderError(
            "cursor_quota_order_unreadable",
            "Stored Cursor order is invalid JSON. Recovery: set a valid order with yoke universe cursor-quota-order set.",
        ) from exc


def pool_preference(pools, *, model):
    return tuple(pools).index(cursor_scope_for_model(model))


def set_pool_order(conn, *, pools, actor_id=None):
    ordered = validate_cursor_quota_order(pools)
    p = marker(conn)
    conn.execute(
        "INSERT INTO universe_settings (key,value,updated_at,updated_by_actor_id) "
        f"VALUES ({p},{p},{p},{p}) ON CONFLICT (key) DO UPDATE SET "
        "value=excluded.value,updated_at=excluded.updated_at,updated_by_actor_id=excluded.updated_by_actor_id",
        (
            KEY,
            json_helper.dumps_compact(list(ordered)),
            instant_parameter(conn, utc_now()),
            actor_id,
        ),
    )
    conn.commit()
    return ordered
