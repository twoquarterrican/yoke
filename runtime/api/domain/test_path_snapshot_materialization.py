# ruff: noqa: F811
"""Large planned snapshots use one update and disposable summary telemetry."""

from unittest.mock import patch

from runtime.api.domain._path_claims_test_helpers import conn  # noqa: F401
from yoke_core.domain.path_snapshot_materialization import materialize_snapshot_targets


def test_bulk_materialization_keeps_identity_and_is_idempotent(conn):
    conn.execute(
        "INSERT INTO path_targets (project_id,kind,path_string,generation,created_at,materialization_state) "
        "SELECT 1,'file','src/file-' || i || '.py',1,'2026-05-01T00:00:00Z', "
        "CASE WHEN i % 2 = 0 THEN 'tentative' ELSE 'planned' END "
        "FROM generate_series(1,622) i"
    )
    ids = [row[0] for row in conn.execute("SELECT id FROM path_targets ORDER BY id")]
    with patch("yoke_core.domain.path_targets_events._emit", return_value=None) as emit:
        count = materialize_snapshot_targets(
            conn, target_ids=ids, project_id=1, commit_sha="a" * 40
        )
        assert count == 622
        assert emit.call_count == 1
        assert emit.call_args.kwargs["context"]["target_count"] == 622
        assert emit.call_args.kwargs["context"]["target_ids"] == ids
        assert (
            materialize_snapshot_targets(
                conn, target_ids=ids, project_id=1, commit_sha="a" * 40
            )
            == 0
        )
        assert emit.call_count == 1
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM path_targets WHERE materialization_state='observed'"
        ).fetchone()[0]
        == 622
    )
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM path_targets").fetchone()[0] == 0


def test_empty_snapshot_emits_nothing(conn):
    with patch("yoke_core.domain.path_targets_events._emit") as emit:
        assert (
            materialize_snapshot_targets(
                conn, target_ids=[], project_id=1, commit_sha="a" * 40
            )
            == 0
        )
    emit.assert_not_called()
