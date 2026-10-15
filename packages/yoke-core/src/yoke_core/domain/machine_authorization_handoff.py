"""Accept hosted device codes into the shared personal-approval store."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from yoke_contracts.timestamps import format_instant, parse_instant
from yoke_core.domain import db_backend
from yoke_core.domain.db_helpers import instant_parameter
from yoke_core.domain.hosted_service_authority import hosted_service_org_ids
from yoke_core.domain.machine_authorization_codes import (
    MachineAuthorizationError,
    SERVER_PENDING_CODES,
    _now,
    _p,
)


def handoff(
    conn: Any,
    *,
    device_hash: str,
    user_code: str,
    machine_id: str,
    machine_name: str,
    platform: str,
    expires_at: str,
    org_id: int,
    actor_id: int,
) -> dict[str, Any]:
    p = _p(conn)
    orgs = hosted_service_org_ids(conn, actor_id)
    if not orgs:
        raise MachineAuthorizationError(
            "permission_denied",
            "call with this universe's hosted service identity",
            403,
        )
    if not conn.execute(
        f"SELECT 1 FROM organizations WHERE id={p}", (org_id,)
    ).fetchone():
        raise MachineAuthorizationError(
            "authorization_org_unknown",
            "select an existing organization and retry",
            404,
        )
    if org_id not in orgs:
        raise MachineAuthorizationError(
            "permission_denied",
            "use the hosted service identity for the target organization",
            403,
        )
    try:
        machine_id = str(UUID(machine_id))
        expires = parse_instant(expires_at)
        valid = re.fullmatch(r"[0-9a-f]{64}", device_hash) and re.fullmatch(
            r"[A-Z0-9]{4}", user_code
        )
        if not valid or not machine_name.strip() or not platform.strip():
            raise ValueError("invalid code or machine facts")
    except (ValueError, TypeError, AttributeError):
        raise MachineAuthorizationError(
            "authorization_handoff_invalid",
            "send a SHA-256 device hash, four uppercase alphanumeric characters, machine UUID/name/platform and a qualified expiry instant",
        ) from None
    now = _now()
    if expires <= now:
        raise MachineAuthorizationError(
            "authorization_expired", "issue a fresh hosted connection code", 410
        )
    # Share start's lock so collision and capacity checks serialize with it.
    if db_backend.connection_is_postgres(conn):
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext('machine_authorization_codes'))"
        )
    for column, value, reason in (
        ("device_hash", device_hash, "authorization_device_code_collision"),
        ("user_code", user_code, "authorization_match_code_collision"),
    ):
        if conn.execute(
            f"SELECT 1 FROM machine_authorization_codes WHERE {column}={p}", (value,)
        ).fetchone():
            raise MachineAuthorizationError(
                reason,
                "issue a new device secret and match code, then retry handoff",
                409,
            )
    count = conn.execute(
        f"SELECT count(*) FROM machine_authorization_codes WHERE consumed_at IS NULL AND expires_at>{p}",
        (instant_parameter(conn, now),),
    ).fetchone()[0]
    if count >= SERVER_PENDING_CODES:
        raise MachineAuthorizationError(
            "authorization_capacity",
            "finish an approval or retry after code expiry",
            429,
        )
    conn.execute(
        "INSERT INTO machine_authorization_codes "
        "(device_hash,user_code,org_id,expires_at,machine_id,machine_name,platform) "
        f"VALUES ({p},{p},{p},{p},{p},{p},{p})",
        (
            device_hash,
            user_code,
            org_id,
            instant_parameter(conn, expires),
            machine_id,
            machine_name,
            platform,
        ),
    )
    conn.commit()
    return {"code": user_code, "org_id": org_id, "expires_at": format_instant(expires)}
