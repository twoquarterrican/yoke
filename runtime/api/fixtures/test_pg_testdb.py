"""Tests for Postgres disposable test database helpers."""

from __future__ import annotations


import pytest

from runtime.api.fixtures import pg_testdb
from yoke_core.domain import pg_test_db_namespace


def test_setup_ambient_test_db_clones_template_and_registers_cleanup(monkeypatch):
    admin_sql = []
    cleanups = []

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
    monkeypatch.setattr(pg_testdb, "_base_dsn", lambda: "host=/tmp dbname=postgres")
    monkeypatch.setattr(pg_testdb, "_admin_execute", lambda sql: admin_sql.append(sql))
    monkeypatch.setattr(pg_testdb.atexit, "register", lambda fn: cleanups.append(fn))
    monkeypatch.setattr(pg_testdb, "_fixture_template_db", lambda: "yoke_test_tmpl")

    name = pg_testdb.setup_ambient_test_db()

    # The worker id keeps two workers apart; the run tag keeps two concurrent
    # invocations apart, which is what makes one shared cluster safe.
    assert f"_{pg_testdb.AMBIENT_DB_PURPOSE}_gw3_" in name
    assert pg_test_db_namespace.belongs_to_current_run(name)
    assert admin_sql == [f'CREATE DATABASE "{name}" TEMPLATE "yoke_test_tmpl"']

    cleanups[0]()
    assert admin_sql[-1] == f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'


def test_fixture_template_and_checkout_share_production_strategy(monkeypatch):
    from runtime.api.fixtures import file_test_db

    calls = []
    monkeypatch.setattr(
        file_test_db,
        "_schema_template_db",
        lambda strategy: calls.append(strategy) or "production-template",
    )
    monkeypatch.setattr(
        file_test_db,
        "_reusable_checkout",
        lambda strategy: calls.append(strategy) or "production-checkout",
    )
    assert pg_testdb._fixture_template_db() == "production-template"
    assert pg_testdb.reusable_fixture_database() == "production-checkout"
    assert calls == [file_test_db._apply_production_schema] * 2


def test_refuses_to_drop_another_invocations_database(monkeypatch):
    """The guard that makes concurrent runs safe without coordinating.

    A run may only ever drop what it created. Reclaiming what an interrupted
    run left behind belongs to the ownership-gated orphan sweep, which first
    checks that the owning process has actually exited.
    """
    dropped = []
    monkeypatch.setattr(pg_testdb, "_base_dsn", lambda: "host=/tmp dbname=postgres")
    monkeypatch.setattr(pg_testdb, "_admin_execute", lambda sql: dropped.append(sql))
    theirs = (
        f"{pg_testdb.TEST_DB_PREFIX}{pg_test_db_namespace.mint_run_tag(pid=31337)}_abc"
    )

    with pytest.raises(RuntimeError, match="another invocation"):
        pg_testdb.drop_test_database(theirs)

    assert dropped == []


def test_refuses_to_operate_on_a_non_test_database():
    with pytest.raises(RuntimeError, match="non-test database"):
        pg_testdb.drop_test_database("production")


def test_production_init_uses_captured_cluster_credentials(monkeypatch):
    from types import SimpleNamespace
    from runtime.api.fixtures import production_schema

    name = pg_test_db_namespace.database_name("authenticated")
    original = "dbname=owned password=fixture-secret"
    bindings = []
    monkeypatch.setattr(
        pg_testdb,
        "dsn_for_test_database",
        lambda supplied: (
            original if supplied == name else pytest.fail("wrong database")
        ),
    )
    monkeypatch.setattr(
        production_schema,
        "run_init_chain",
        lambda **_kwargs: bindings.append(pg_testdb.db_backend.resolve_pg_dsn()),
    )
    monkeypatch.setattr(
        production_schema, "seed_project_identities", lambda _conn: None
    )
    conn = SimpleNamespace(
        info=SimpleNamespace(dbname=name, dsn="dbname=owned"),
        execute=lambda *_args: None,
        commit=lambda: None,
    )
    before = pg_testdb.db_backend.resolve_pg_dsn()
    production_schema.initialize_test_schema(conn)
    assert bindings == [original]
    assert pg_testdb.db_backend.resolve_pg_dsn() == before
