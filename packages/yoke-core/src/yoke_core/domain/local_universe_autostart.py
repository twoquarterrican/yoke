"""Start this machine's stopped embedded Postgres before a step needs it.

A machine restart stops the embedded cluster and leaves its data directory
initialized. A step that reads or copies into that cluster — local-Postgres
dispatch, a universe export, a release fleet rehearsal — starts it exactly as
`yoke local-postgres start` would rather than failing on a missing socket.
A cluster that was never initialized is refused with the command that makes it.
"""

from __future__ import annotations

from typing import Callable, Optional

from yoke_core.domain import local_universe
from yoke_core.domain.postgres_cluster import ClusterSpec


def ensure_running(
    spec: Optional[ClusterSpec] = None,
    *,
    emit: Callable[[str], None] = lambda _line: None,
) -> None:
    """Idempotently start an initialized embedded cluster that is not running."""
    state = local_universe.status(spec)
    if state["running"]:
        return
    if not state["initialized"]:
        raise local_universe.LocalUniverseError(
            f"the embedded Postgres at {state['root']} is not initialized; "
            "run `yoke local-postgres start` (or `yoke setup --local`) and retry"
        )
    emit(
        f"starting the stopped embedded Postgres at {state['root']} "
        "(same as `yoke local-postgres start`)"
    )
    local_universe.start(spec, emit=emit)


__all__ = ["ensure_running"]
