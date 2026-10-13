"""Schema callable templates preserve seeds, isolation and build failures."""

import os

import pytest

from runtime.api.fixtures import file_test_db, pg_reusable_db, pg_testdb
from yoke_core.domain import db_backend, schema


def _rows():
    with db_backend.connect_psycopg() as conn:
        return conn.execute("SELECT id FROM template_seed ORDER BY id").fetchall()


def _strategy(builds):
    def apply():
        builds.append(True)
        with db_backend.connect_psycopg() as conn:
            conn.execute("CREATE TABLE template_seed (id INTEGER)")
            conn.execute("INSERT INTO template_seed VALUES (7)")

    return apply


def test_custom_callable_builds_once_and_restores_seed_rows(tmp_path):
    builds = []
    apply = _strategy(builds)
    with file_test_db.init_test_db(tmp_path, apply):
        with db_backend.connect_psycopg() as conn:
            first = conn.execute("SELECT current_database()").fetchone()[0]
            conn.execute("DELETE FROM template_seed")
    with file_test_db.init_test_db(tmp_path, apply):
        assert _rows() == [(7,)]
        with db_backend.connect_psycopg() as conn:
            assert conn.execute("SELECT current_database()").fetchone()[0] == first
    assert builds == [True]


def test_nested_custom_context_and_ddl_drift_clone_without_rebuilding(tmp_path):
    builds = []
    apply = _strategy(builds)
    prior = os.environ.get(db_backend.PG_DSN_ENV)
    with file_test_db.init_test_db(tmp_path, apply):
        outer = os.environ[db_backend.PG_DSN_ENV]
        with file_test_db.init_test_db(tmp_path, apply):
            assert os.environ[db_backend.PG_DSN_ENV] != outer
            assert _rows() == [(7,)]
            with db_backend.connect_psycopg() as conn:
                conn.execute("DELETE FROM template_seed")
        assert os.environ[db_backend.PG_DSN_ENV] == outer
        assert _rows() == [(7,)]
        with db_backend.connect_psycopg() as conn:
            conn.execute("DROP TABLE template_seed")
    with file_test_db.init_test_db(tmp_path, apply):
        assert _rows() == [(7,)]
    assert builds == [True]
    assert os.environ.get(db_backend.PG_DSN_ENV) == prior


def test_distinct_same_named_callables_have_distinct_templates(tmp_path):
    first_builds, second_builds = [], []
    first, second = _strategy(first_builds), _strategy(second_builds)
    assert first.__qualname__ == second.__qualname__
    with file_test_db.init_test_db(tmp_path, first):
        first_dsn = os.environ[db_backend.PG_DSN_ENV]
    with file_test_db.init_test_db(tmp_path, second):
        assert os.environ[db_backend.PG_DSN_ENV] != first_dsn
    assert first_builds == second_builds == [True]


def test_unhashable_callable_uses_identity(tmp_path):
    class Strategy:
        __hash__ = None

        def __init__(self):
            self.builds = []

        def __call__(self):
            _strategy(self.builds)()

    apply = Strategy()
    for _ in range(2):
        with file_test_db.init_test_db(tmp_path, apply):
            assert _rows() == [(7,)]
    assert apply.builds == [True]


def test_failed_template_is_dropped_and_restores_dsn(tmp_path, monkeypatch):
    builds, dropped = [], []
    apply = _strategy(builds)
    original = pg_testdb.drop_test_database

    def drop(name, **kwargs):
        dropped.append(name)
        return original(name, **kwargs)

    monkeypatch.setattr(pg_testdb, "drop_test_database", drop)
    prior = os.environ.get(db_backend.PG_DSN_ENV)

    def failing():
        apply()
        raise RuntimeError("schema build refused")

    with pytest.raises(RuntimeError, match="schema build refused"):
        with file_test_db.init_test_db(tmp_path, failing):
            pytest.fail("failed schema must never be yielded")
    assert len(dropped) == 1
    assert id(failing) not in file_test_db._SCHEMA_TEMPLATES
    assert os.environ.get(db_backend.PG_DSN_ENV) == prior


def test_explicit_production_init_shares_default_flavor(tmp_path):
    with file_test_db.init_test_db(tmp_path):
        first = os.environ[db_backend.PG_DSN_ENV]
    with file_test_db.init_test_db(tmp_path, schema.cmd_init):
        assert os.environ[db_backend.PG_DSN_ENV] == first


def test_fixture_human_strategy_is_reused_and_resets_actor_data(tmp_path):
    from runtime.api.fixtures.backlog import apply_fixture_schema_with_human

    with file_test_db.init_test_db(tmp_path, apply_fixture_schema_with_human):
        first = os.environ[db_backend.PG_DSN_ENV]
        with db_backend.connect_psycopg() as conn:
            baseline = conn.execute(
                "SELECT id, name FROM actors ORDER BY id"
            ).fetchall()
            assert baseline
            conn.execute("UPDATE actors SET name = 'changed'")
    with file_test_db.init_test_db(tmp_path, apply_fixture_schema_with_human):
        assert os.environ[db_backend.PG_DSN_ENV] == first
        with db_backend.connect_psycopg() as conn:
            assert (
                conn.execute("SELECT id, name FROM actors ORDER BY id").fetchall()
                == baseline
            )
    pg_reusable_db.discard(id(apply_fixture_schema_with_human))
