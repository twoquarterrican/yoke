"""Expired read handlers unwind and retain a named, observable refusal."""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from yoke_contracts.api.function_call import HandlerOutcome
from yoke_contracts.read_deadline import (
    ReadDeadlineExceeded,
    active,
    read_budget,
    remaining_seconds,
)
from yoke_core.domain import function_read_deadline as deadline
from yoke_core.domain.bounded_database import BudgetConnection
from runtime.api.domain.test_yoke_function_dispatch import (
    _DispatcherTestBase,
    _Req,
    _Resp,
    _make_request,
    _stable_kwargs,
)
from yoke_core.domain.yoke_function_registry import register
from yoke_core.domain.yoke_function_dispatch import dispatch
from yoke_core.domain import yoke_function_dispatch_events as events


@pytest.mark.parametrize("threaded", [False, True])
def test_read_loop_stops_before_finishing_and_restores_context(monkeypatch, threaded):
    monkeypatch.setattr(deadline, "FUNCTION_RESPONSE_TIMEOUT_SECONDS", 0.03)
    monkeypatch.setattr(deadline, "READ_RESPONSE_RESERVE_SECONDS", 0)
    finished = []

    def handler(request):
        try:
            while True:
                pass
        except Exception:
            finished.append("swallowed")
        finished.append("completed")

    def run():
        trace = sys.gettrace()
        start = time.monotonic()
        result = deadline.invoke_handler(
            SimpleNamespace(
                side_effects=(),
                function_id="qa.plan.list",
                handler=handler,
            ),
            _make_request("qa.plan.list"),
        )
        assert time.monotonic() - start < 1
        assert result.error.code == "read_deadline_exceeded"
        assert "--limit" in result.error.recovery_hint
        assert not active()
        assert sys.gettrace() is trace

    if threaded:
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(run).result(timeout=2)
    else:
        run()
    assert finished == []


def test_mutation_keeps_its_handler_without_a_read_budget():
    observed = []

    def handler(request):
        observed.append(active())
        return HandlerOutcome(primary_success=True)

    result = deadline.invoke_handler(
        SimpleNamespace(
            side_effects=("database",),
            function_id="items.create",
            handler=handler,
        ),
        _make_request("items.create"),
    )
    assert result.primary_success
    assert observed == [False]


def test_sql_timeout_is_the_remaining_request_budget():
    statements = []

    class Cursor:
        def execute(self, sql, params=()):
            statements.append((sql, params))
            failure = Exception("statement cancelled")
            failure.sqlstate = "57014"
            raise failure

    class Connection:
        autocommit = False

        def execute(self, sql, params):
            statements.append((sql, params))

        def cursor(self):
            return Cursor()

    with read_budget(0.5):
        conn = BudgetConnection(
            Connection(),
            remaining=lambda: remaining_seconds(30),
            driver_call=deadline.driver_call,
        )
        with pytest.raises(ReadDeadlineExceeded):
            conn.execute("SELECT pg_sleep(1)")
    assert statements[0][0] == "SELECT set_config('statement_timeout', %s, %s)"
    assert 0 < int(statements[0][1][0][:-2]) <= 500
    assert not active()


class TestDeadlineEvent(_DispatcherTestBase):
    def test_dispatch_records_refused_read_on_called_event(self):
        completed = []

        def handler(request):
            while True:
                pass
            completed.append(True)

        register("test.expired_read", handler, _Req, _Resp, **_stable_kwargs())
        with (
            patch.object(deadline, "FUNCTION_RESPONSE_TIMEOUT_SECONDS", 0.03),
            patch.object(deadline, "READ_RESPONSE_RESERVE_SECONDS", 0),
        ):
            response = dispatch(_make_request("test.expired_read"))
        assert response.error.code == "read_deadline_exceeded"
        called = [
            row
            for row in events.emit_event.calls
            if row["args"] and row["args"][0] == "YokeFunctionCalled"
        ]
        assert len(called) == 1
        assert called[0]["kwargs"]["outcome"] == "failed"
        assert called[0]["kwargs"]["context"]["error_code"] == "read_deadline_exceeded"
        assert completed == []


def test_postgres_stops_the_query_before_the_handler_can_finish():
    from runtime.api.fixtures import pg_testdb
    from yoke_core.domain import db_backend

    name = pg_testdb.create_test_database()
    completed = []
    started = time.monotonic()
    try:
        with db_backend.bound_pg_dsn(pg_testdb.dsn_for_test_database(name)):
            # Open outside the short test budget so this proves SQL cancellation,
            # independently of database startup and local socket acquisition.
            with db_backend.connect() as native:
                with pytest.raises(ReadDeadlineExceeded):
                    with read_budget(0.15):
                        conn = BudgetConnection(
                            native,
                            remaining=lambda: remaining_seconds(30),
                            driver_call=deadline.driver_call,
                        )
                        conn.execute("SELECT pg_sleep(2)")
                        completed.append(True)
    finally:
        pg_testdb.drop_test_database(name)
    assert completed == []
    assert time.monotonic() - started < 2
