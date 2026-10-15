"""Authenticate hosted polling, then reuse the shared one-time delivery owner."""

from typing import Any

from yoke_core.domain import machine_authorization_codes as codes
from yoke_core.domain.actor_state import ActorDisabledError
from yoke_core.domain.machine_authorization_handoff import require_service_org
from yoke_core.domain.machine_registry import MachineRegistryError


def handoff_poll(
    conn: Any,
    *,
    device_code: str,
    machine_id: str,
    machine_name: str,
    org_id: int,
    actor_id: int,
) -> dict[str, Any]:
    require_service_org(conn, actor_id, org_id)
    try:
        row = codes._row(
            conn,
            "device_hash",
            codes._hash(device_code),
            lock=True,
            inspect_closed=True,
        )
    except codes.MachineAuthorizationError:
        raise codes.MachineAuthorizationError(
            "authorization_unknown", "start a fresh hosted connection code", 404
        ) from None
    if row["org_id"] != org_id:
        raise codes.MachineAuthorizationError(
            "permission_denied",
            "poll through the engine organization that accepted this code",
            403,
        )
    try:
        credential = codes.poll(
            conn,
            device_code=device_code,
            machine_id=machine_id,
            machine_name=machine_name,
            origin="",
        )
    except codes.MachineAuthorizationError as exc:
        states = {
            "authorization_pending": "pending",
            "authorization_denied": "denied",
            "authorization_expired": "expired",
            "authorization_consumed": "consumed",
        }
        if exc.code not in states:
            raise
        return {"state": states[exc.code], "machine_id": row["machine_id"]}
    except MachineRegistryError as exc:
        raise codes.MachineAuthorizationError(
            exc.code,
            f"{exc}; reconnect as the machine owner or ask an admin to inspect it",
            403,
        ) from None
    except ActorDisabledError as exc:
        raise codes.MachineAuthorizationError("actor_disabled", str(exc), 403) from None
    return {
        "state": "approved",
        "machine_id": row["machine_id"],
        "token": credential["token"],
    }
