"""Reusing ambient control-plane Postgres connections within one process.

Opening a control-plane connection is the expensive part of a call: through
an operator's SSH forward to Aurora, TLS plus password authentication costs
about three seconds, against milliseconds for the statements that follow. A
process that makes many registered calls or event writes -- the API server,
a deployment driver on the local-postgres transport -- therefore keeps a
few authenticated connections and hands them out again.

Each lease is still one unit of work. :class:`ReusedConnection` behaves like
the psycopg connection it wraps, but ``close()`` (and leaving a ``with``
block) returns the socket here instead of closing it, and detaches the lease
so a stale reference cannot touch the next holder's session. Returning rolls
back any open transaction -- exactly what closing did -- and resets session
state (settings, advisory locks, cursors, listens, temp tables), so nothing
one lease set is visible to the next. A returned socket that fails its reset
or its liveness check on the next checkout is closed and a fresh one opened
through the caller's normal connect path, so readiness self-heal and managed
secret rotation recovery still see every real connect failure.

Only idle sockets are retained, at most :data:`MAX_IDLE_CONNECTIONS` per
process and none older than :data:`MAX_IDLE_SECONDS`; in-use connections are
bounded by the caller's own concurrency, as before.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

MAX_IDLE_CONNECTIONS = 4
MAX_IDLE_SECONDS = 60.0

TEST_TRACK_CONNECTIONS_ENV = "YOKE_TEST_TRACK_PG_CONNECTIONS"

# Same order and coverage as DISCARD ALL, minus DEALLOCATE ALL and DISCARD
# PLANS: psycopg keeps its own record of server-side prepared statements and
# does not notice a DEALLOCATE it did not issue, so those statements must
# survive the reset.
SESSION_RESET_SQL = (
    "CLOSE ALL; UNLISTEN *; RESET ALL; SELECT pg_advisory_unlock_all(); "
    "DISCARD TEMP; DISCARD SEQUENCES"
)

_LOCK = threading.Lock()
_IDLE: list[tuple[str, Any, float]] = []
_TRACKED_TEST_CONNECTIONS: list[Any] = []
# A forked child shares its parent's sockets; closing them would terminate the
# parent's sessions, so the child keeps these references and never uses them.
_INHERITED_FROM_PARENT: list[Any] = []


def _forget_parent_connections() -> None:
    _INHERITED_FROM_PARENT.extend(entry[1] for entry in _IDLE)
    _IDLE.clear()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_forget_parent_connections)


class ReusedConnection:
    """A leased psycopg connection whose ``close()`` returns it for reuse."""

    def __init__(self, conn, dsn: str):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_dsn", dsn)

    def _leased(self):
        conn = object.__getattribute__(self, "_conn")
        if conn is None:
            import psycopg

            raise psycopg.OperationalError(
                "the connection is closed: it was returned for reuse; "
                "open a new one with db_backend.connect()"
            )
        return conn

    def __getattr__(self, name):
        return getattr(self._leased(), name)

    def __setattr__(self, name, value):
        # Only psycopg connection properties reach the shared socket; any other
        # assignment (a patched method, say) must not outlive this lease.
        conn = object.__getattribute__(self, "_conn")
        if conn is not None and isinstance(getattr(type(conn), name, None), property):
            setattr(conn, name, value)
        else:
            object.__setattr__(self, name, value)

    @property
    def closed(self) -> bool:
        return self._conn is None or self._conn.closed

    @property
    def broken(self) -> bool:
        return self._conn is not None and self._conn.broken

    def close(self) -> None:
        conn = self._conn
        if conn is None:
            return
        object.__setattr__(self, "_conn", None)
        _return(self._dsn, conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        conn = self._conn
        if conn is None or conn.closed:
            return
        try:
            if exc_type is None:
                conn.commit()
            else:
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001 -- keep the caller's error
                    pass
        finally:
            self.close()


def _close_quietly(conn) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001 -- the socket is being discarded anyway
        pass


def _reset_for_reuse(conn) -> bool:
    import psycopg
    from psycopg.pq import TransactionStatus

    if conn.closed or conn.broken:
        return False
    try:
        if conn.info.transaction_status != TransactionStatus.IDLE:
            conn.rollback()
        conn.autocommit = True
        conn.execute(SESSION_RESET_SQL)
    except psycopg.Error:
        return False
    return True


def _return(dsn: str, conn) -> None:
    if not _reset_for_reuse(conn):
        _close_quietly(conn)
        return
    with _LOCK:
        _IDLE.append((dsn, conn, time.monotonic()))
        evicted = [entry[1] for entry in _IDLE[:-MAX_IDLE_CONNECTIONS]]
        del _IDLE[:-MAX_IDLE_CONNECTIONS]
    for stale in evicted:
        _close_quietly(stale)


def _is_alive(conn) -> bool:
    import psycopg

    if conn.closed or conn.broken:
        return False
    try:
        conn.execute("")
    except psycopg.Error:
        return False
    return True


def _take_idle(dsn: str):
    while True:
        with _LOCK:
            index = next(
                (i for i in range(len(_IDLE) - 1, -1, -1) if _IDLE[i][0] == dsn),
                None,
            )
            if index is None:
                return None
            _, conn, returned_at = _IDLE.pop(index)
        if time.monotonic() - returned_at <= MAX_IDLE_SECONDS and _is_alive(conn):
            return conn
        _close_quietly(conn)


def lease(
    dsn: str,
    *,
    autocommit: bool,
    row_factory: Callable,
    connect: Callable[[str], Any],
):
    """Return a connection to *dsn*: an idle authenticated one, or ``connect(dsn)``.

    *connect* opens a raw guarded psycopg connection; its failures propagate
    unchanged. The caller applies the read-deadline wrapper to the result.
    """
    conn = _take_idle(dsn)
    if conn is None:
        conn = connect(dsn)
    conn.autocommit = autocommit
    conn.row_factory = row_factory
    return ReusedConnection(conn, dsn)


def idle_connection_count() -> int:
    with _LOCK:
        return len(_IDLE)


def close_idle_connections() -> None:
    """Close every retained idle connection in this process."""
    with _LOCK:
        idle = [entry[1] for entry in _IDLE]
        _IDLE.clear()
    for conn in idle:
        _close_quietly(conn)


def track_test_connection(conn):
    if os.environ.get(TEST_TRACK_CONNECTIONS_ENV) == "1":
        _TRACKED_TEST_CONNECTIONS.append(conn)
    return conn


def tracked_test_connection_count() -> int:
    """Return the current test connection tracker position."""
    return len(_TRACKED_TEST_CONNECTIONS)


def close_test_connections_since(index: int) -> None:
    """Close connections a pytest item leaked after *index*, then drain reuse.

    The active runtime does not enable tracking. Pytest turns it on so native
    psycopg connections left open by fixture shapes cannot accumulate across a
    broad xdist run and exhaust the shared test Postgres service, and so no
    idle socket outlives the test database it was opened against.
    """
    connections = list(reversed(_TRACKED_TEST_CONNECTIONS[index:]))
    del _TRACKED_TEST_CONNECTIONS[index:]
    for conn in connections:
        _close_quietly(conn)
    close_idle_connections()


__all__ = [
    "MAX_IDLE_CONNECTIONS",
    "MAX_IDLE_SECONDS",
    "ReusedConnection",
    "SESSION_RESET_SQL",
    "TEST_TRACK_CONNECTIONS_ENV",
    "close_idle_connections",
    "close_test_connections_since",
    "idle_connection_count",
    "lease",
    "track_test_connection",
    "tracked_test_connection_count",
]
