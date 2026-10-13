"""Shared SQL statement budgeting, preserving native connection semantics."""

from __future__ import annotations
from yoke_core.domain import db_backend


class BudgetCursor:
    def __init__(self, cursor, conn):
        self._cursor = cursor
        self._conn = conn

    def __getattr__(self, name):
        value = getattr(self._cursor, name)
        if callable(value):
            return lambda *a, **k: self._conn._driver_call(value, *a, **k)
        return value

    def __enter__(self):
        self._conn._driver_call(self._cursor.__enter__)
        return self

    def __exit__(self, *args):
        return self._conn._driver_call(self._cursor.__exit__, *args)

    def __iter__(self):
        iterator = self._conn._driver_call(iter, self._cursor)
        while True:
            try:
                row = self._conn._driver_call(next, iterator)
            except StopIteration:
                return
            self._conn._remaining()
            yield row

    def _execute(self, method, *args, **kwargs):
        self._conn._set_timeout()
        self._conn._driver_call(getattr(self._cursor, method), *args, **kwargs)
        self._conn._remaining()
        return self

    def execute(self, *args, **kwargs):
        return self._execute("execute", *args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._execute("executemany", *args, **kwargs)


class BudgetConnection:
    def __init__(self, conn, *, remaining, driver_call):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_remaining", remaining)
        object.__setattr__(self, "_driver_call", driver_call)

    def __getattr__(self, name):
        value = getattr(self._conn, name)
        if callable(value):
            return lambda *a, **k: self._driver_call(value, *a, **k)
        return value

    def __setattr__(self, name, value):
        setattr(self._conn, name, value)

    def _set_timeout(self):
        timeout_ms = max(1, int(self._remaining() * 1000))
        if db_backend.connection_is_postgres(self._conn):
            self._driver_call(
                self._conn.execute,
                "SELECT set_config('statement_timeout', %s, %s)",
                (f"{timeout_ms}ms", not self._conn.autocommit),
            )

    def cursor(self, *args, **kwargs):
        return BudgetCursor(self._driver_call(self._conn.cursor, *args, **kwargs), self)

    def execute(self, *args, **kwargs):
        return self.cursor().execute(*args, **kwargs)

    def __enter__(self):
        self._driver_call(self._conn.__enter__)
        return self

    def __exit__(self, *args):
        return self._driver_call(self._conn.__exit__, *args)
