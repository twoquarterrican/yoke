"""Report-local SQL reuse preserves independent cursors and live boundaries."""

import sqlite3

from yoke_core.domain.steering_report_read_connection import ReportReadConnection


def test_reads_share_one_query_and_independent_cursors():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE facts (value INTEGER)")
    conn.executemany("INSERT INTO facts VALUES (?)", [(1,), (2,)])
    queries = []
    conn.set_trace_callback(queries.append)
    report = ReportReadConnection(conn)
    first = report.execute("SELECT value FROM facts")
    assert first.fetchone() == (1,)
    assert report.execute("SELECT value FROM facts").fetchall() == [(1,), (2,)]
    assert first.fetchall() == [(2,)]
    assert len(queries) == 1
    ReportReadConnection(conn).execute("SELECT value FROM facts").fetchall()
    assert len(queries) == 2


def test_mutation_and_rollback_invalidate_rows():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE facts (value INTEGER)")
    conn.commit()
    report = ReportReadConnection(conn)
    assert report.execute("SELECT value FROM facts").fetchall() == []
    report.execute("INSERT INTO facts VALUES (?)", (3,))
    assert report.execute("SELECT value FROM facts").fetchone() == (3,)
    report.rollback()
    assert report.execute("SELECT value FROM facts").fetchall() == []
