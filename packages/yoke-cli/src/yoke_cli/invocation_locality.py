"""Mark one invocation's context when its control plane is reached over https.

The ``yoke`` router wraps every adapter in this mark, and the hook evaluator
wraps its in-process fallback in it, so engine code either one runs locally
refuses a direct database connection the caller's machine cannot have.
"""

from __future__ import annotations

import contextlib
from typing import Optional

from yoke_cli.config import machine_config
from yoke_contracts.control_plane_locality import (
    local_authority_is_pinned,
    remote_control_plane,
)
from yoke_contracts.machine_config.schema import TRANSPORT_HTTPS


def control_plane_is_remote(explicit_env: Optional[str]) -> bool:
    """Return whether this invocation has no local database it could open.

    An explicitly pinned DSN answers False whatever the machine config says:
    that pin IS a local authority, it already wins inside the DSN resolver,
    and a machine reached over https can still be handed one for a break-glass
    admin session. Otherwise the declared transport decides — keyed on the
    transport alone, not on a resolved relay target, because a missing token
    changes whether the relay can run, never whether a database exists to open
    instead. Any machine-config problem answers False, leaving the guard off
    and the pre-existing error for that problem to surface where it already
    does.
    """
    if local_authority_is_pinned():
        return False
    try:
        connection = machine_config.active_connection(explicit_env=explicit_env)
    except Exception:  # noqa: BLE001 - config problems are reported elsewhere
        return False
    return str(connection.get("transport") or "") == TRANSPORT_HTTPS


def control_plane_locality(explicit_env: Optional[str]):
    """Return the locality context this invocation's adapter runs under."""
    if control_plane_is_remote(explicit_env):
        return remote_control_plane()
    return contextlib.nullcontext()


__all__ = ["control_plane_is_remote", "control_plane_locality"]
