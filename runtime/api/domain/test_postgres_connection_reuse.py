"""Ambient control-plane connections are reused across calls in one process."""

from __future__ import annotations

import psycopg
import pytest

from yoke_core.domain import db_backend
from yoke_core.domain import postgres_connection_reuse as reuse
from runtime.api.fixtures.pg_testdb import test_database as pg_test_database


@pytest.fixture
def pg_authority():
    reuse.close_idle_connections()
    with pg_test_database():
        yield
    reuse.close_idle_connections()


@pytest.fixture
def socket_opens(monkeypatch):
    opened = []
    real = db_backend.connect_guarded_socket

    def counting(dsn, **kwargs):
        opened.append(dsn)
        return real(dsn, **kwargs)

    monkeypatch.setattr(db_backend, "connect_guarded_socket", counting)
    return opened


def _backend_pid(conn) -> int:
    return conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]


def test_sequential_calls_reuse_one_connection(pg_authority, socket_opens):
    pids = set()
    for _ in range(5):
        conn = db_backend.connect()
        try:
            pids.add(_backend_pid(conn))
        finally:
            conn.close()

    assert len(pids) == 1
    assert len(socket_opens) == 1
    assert reuse.idle_connection_count() == 1


def test_connect_psycopg_reuses_with_tuple_rows(pg_authority, socket_opens):
    with db_backend.connect() as conn:
        native_pid = _backend_pid(conn)
    tuple_conn = db_backend.connect_psycopg()
    try:
        assert tuple_conn.execute("SELECT pg_backend_pid()").fetchone() == (native_pid,)
    finally:
        tuple_conn.close()
    assert len(socket_opens) == 1


def test_returned_connection_is_detached(pg_authority):
    conn = db_backend.connect()
    conn.close()
    conn.close()

    assert conn.closed
    with pytest.raises(psycopg.OperationalError, match="returned for reuse"):
        conn.execute("SELECT 1")


def test_open_transaction_is_rolled_back_on_close(pg_authority):
    conn = db_backend.connect()
    conn.execute("CREATE TABLE reuse_uncommitted_probe (n int)")
    conn.close()

    with db_backend.connect() as conn:
        found = conn.execute(
            "SELECT to_regclass('reuse_uncommitted_probe') AS t"
        ).fetchone()["t"]
    assert found is None


def test_with_block_commits_and_returns(pg_authority, socket_opens):
    with db_backend.connect() as conn:
        conn.execute("CREATE TABLE reuse_committed_probe (n int)")
    assert conn.closed

    with db_backend.connect() as conn:
        found = conn.execute(
            "SELECT to_regclass('reuse_committed_probe') AS t"
        ).fetchone()["t"]
        conn.execute("DROP TABLE reuse_committed_probe")
    assert found is not None
    assert len(socket_opens) == 1


def test_session_state_does_not_leak_to_the_next_lease(pg_authority):
    conn = db_backend.connect()
    conn.autocommit = True
    first_pid = _backend_pid(conn)
    conn.execute("SET statement_timeout = '1234ms'")
    conn.execute("SELECT pg_advisory_lock(424242)")
    conn.execute("CREATE TEMP TABLE reuse_temp_probe (n int)")
    conn.execute("LISTEN reuse_probe_channel")
    conn.close()

    with db_backend.connect() as conn:
        assert _backend_pid(conn) == first_pid
        assert conn.autocommit is False
        settings = conn.execute(
            "SELECT current_setting('statement_timeout') AS statement_timeout, "
            "current_setting('idle_in_transaction_session_timeout') AS idle_guard, "
            "to_regclass('pg_temp.reuse_temp_probe') AS temp_table, "
            "(SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
            " AND pid = pg_backend_pid()) AS advisory_locks, "
            "(SELECT count(*) FROM pg_listening_channels()) AS listens"
        ).fetchone()

    assert settings["statement_timeout"] == "0"
    assert settings["idle_guard"] == "2min"
    assert settings["temp_table"] is None
    assert settings["advisory_locks"] == 0
    assert settings["listens"] == 0


def test_prepared_statements_survive_reuse(pg_authority):
    for _ in range(2):
        with db_backend.connect() as conn:
            for n in range(conn.prepare_threshold + 2):
                row = conn.execute("SELECT %s::int AS n", (n,)).fetchone()
                assert row["n"] == n


def test_terminated_idle_connection_is_replaced(pg_authority, socket_opens):
    with db_backend.connect() as conn:
        dead_pid = _backend_pid(conn)
    with psycopg.connect(db_backend.resolve_pg_dsn(), autocommit=True) as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (dead_pid,))

    with db_backend.connect() as conn:
        assert _backend_pid(conn) != dead_pid
    assert len(socket_opens) == 2


def test_expired_idle_connection_is_replaced(pg_authority, socket_opens, monkeypatch):
    monkeypatch.setattr(reuse, "MAX_IDLE_SECONDS", -1.0)
    with db_backend.connect() as conn:
        first_pid = _backend_pid(conn)
    with db_backend.connect() as conn:
        assert _backend_pid(conn) != first_pid
    assert len(socket_opens) == 2


def test_idle_connections_are_bounded(pg_authority):
    leased = [db_backend.connect() for _ in range(reuse.MAX_IDLE_CONNECTIONS + 2)]
    for conn in leased:
        conn.close()

    assert reuse.idle_connection_count() == reuse.MAX_IDLE_CONNECTIONS


class _DummyConn:
    def __init__(self):
        self.closed = 0

    def close(self):
        self.closed += 1


def test_test_connection_tracker_disabled_by_default(monkeypatch):
    reuse.close_test_connections_since(0)
    monkeypatch.delenv(reuse.TEST_TRACK_CONNECTIONS_ENV, raising=False)
    conn = _DummyConn()

    assert reuse.track_test_connection(conn) is conn
    reuse.close_test_connections_since(0)

    assert conn.closed == 0


def test_test_connection_tracker_closes_only_connections_after_snapshot(monkeypatch):
    reuse.close_test_connections_since(0)
    monkeypatch.setenv(reuse.TEST_TRACK_CONNECTIONS_ENV, "1")
    fixture_conn = _DummyConn()
    test_conn = _DummyConn()

    reuse.track_test_connection(fixture_conn)
    baseline = reuse.tracked_test_connection_count()
    reuse.track_test_connection(test_conn)
    reuse.close_test_connections_since(baseline)

    assert fixture_conn.closed == 0
    assert test_conn.closed == 1
    reuse.close_test_connections_since(0)
    reuse.close_test_connections_since(0)
    assert fixture_conn.closed == 1


def test_test_teardown_drains_idle_connections(pg_authority):
    db_backend.connect().close()
    assert reuse.idle_connection_count() == 1

    reuse.close_test_connections_since(reuse.tracked_test_connection_count())

    assert reuse.idle_connection_count() == 0
