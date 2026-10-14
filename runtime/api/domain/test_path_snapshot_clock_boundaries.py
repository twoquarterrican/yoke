"""Path resolution preserves native PostgreSQL clocks."""

from datetime import datetime, timedelta, timezone

import pytest

from yoke_contracts.timestamps import InvalidInstant
from yoke_core.domain.path_registry import (
    KIND_DIRECTORY,
    KIND_FILE,
    ROOT_PATH_SENTINEL,
    _resolve_path_target_id,
)
from yoke_core.domain.path_snapshot_targets import resolve_snapshot_target_ids


@pytest.fixture
def clock_connection(test_db):
    test_db.execute("""CREATE TEMP TABLE projects (
        id INTEGER PRIMARY KEY, slug TEXT, name TEXT, public_item_prefix TEXT
    )""")
    test_db.execute(
        "INSERT INTO projects VALUES (1, 'clock-project', 'Clock project', 'CLK')"
    )
    test_db.execute("""CREATE TEMP TABLE path_targets (
        id SERIAL PRIMARY KEY, project_id INTEGER, kind TEXT, path_string TEXT,
        generation INTEGER, parent_target_id INTEGER,
        materialization_state TEXT DEFAULT 'observed', created_at TIMESTAMPTZ
    )""")
    test_db.execute("""CREATE TEMP TABLE path_snapshots (
        id INTEGER PRIMARY KEY, project_id INTEGER, commit_sha TEXT,
        built_at TIMESTAMPTZ
    )""")
    test_db.execute("""CREATE TEMP TABLE path_snapshot_entries (
        snapshot_id INTEGER, target_id INTEGER
    )""")
    return test_db


@pytest.fixture(params=["single", "bulk"])
def target_writer(request):
    def write(conn, observed_at):
        if request.param == "single":
            return _resolve_path_target_id(
                conn, 1, "clock.py", KIND_FILE, None, observed_at
            )
        return resolve_snapshot_target_ids(
            conn,
            project_id=1,
            targets=[(ROOT_PATH_SENTINEL, KIND_DIRECTORY), ("clock.py", KIND_FILE)],
            observed_at=observed_at,
        ).target_ids["clock.py"]

    return write


@pytest.mark.parametrize("offset", [0, 330, -240])
@pytest.mark.parametrize("microsecond", [0, 123456])
def test_target_clock_keeps_native_type(
    clock_connection,
    target_writer,
    offset,
    microsecond,
):
    conn = clock_connection
    instant = datetime(1969, 12, 31, 23, 59, 59, microsecond, tzinfo=timezone.utc)
    supplied = instant.astimezone(timezone(timedelta(minutes=offset)))
    target_id = target_writer(conn, supplied)
    stored = conn.execute(
        "SELECT created_at FROM path_targets WHERE path_string='clock.py'"
    ).fetchone()[0]
    assert isinstance(stored, datetime)
    assert stored == instant
    assert target_writer(conn, supplied) == target_id


@pytest.mark.parametrize("reuse", [False, True])
@pytest.mark.parametrize("bad", [datetime(2026, 1, 1), "2026-01-01T00:00:00Z"])
def test_target_resolution_refuses_non_native_clock_even_when_reusing(
    clock_connection,
    target_writer,
    reuse,
    bad,
):
    conn = clock_connection
    if reuse:
        target_writer(
            conn, datetime(1969, 12, 31, 23, 59, 59, 123456, tzinfo=timezone.utc)
        )
    before = [
        tuple(row)
        for row in conn.execute("SELECT * FROM path_targets ORDER BY id").fetchall()
    ]
    with pytest.raises(InvalidInstant, match="invalid_instant"):
        target_writer(conn, bad)
    after = [
        tuple(row)
        for row in conn.execute("SELECT * FROM path_targets ORDER BY id").fetchall()
    ]
    assert after == before
