"""Hook-mode chunked HTTPS tests for ``yoke project snapshot sync``.

The git post-commit hook sends HEAD identity only; these pin what the
chunked begin answers for it.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from yoke_cli.transport.https import HttpsConnection
from yoke_contracts.api.function_call import FunctionCallResponse
from runtime.api.cli.project_snapshot_cli_test_helpers import (
    CALLS,
    OVERSIZED_HTTPS_PAYLOAD_BYTES,
    head_sha,
    make_repo,
    non_progress_err,
    run_cli,
)


def _force_https_chunking():
    return patch(
        "yoke_cli.commands.adapters.project_snapshot_chunk_sizing"
        ".snapshot_sync_payload_size_bytes",
        return_value=OVERSIZED_HTTPS_PAYLOAD_BYTES,
    )


def _https_connection():
    return patch(
        "yoke_cli.commands.adapters.project_snapshot_chunk_sizing"
        ".resolve_https_connection",
        return_value=HttpsConnection(api_url="https://env.example", token="t"),
    )


def test_hook_mode_identity_only_settles_at_begin(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    commit_sha = head_sha(repo)
    begin_identity_only = FunctionCallResponse(
        success=True,
        function="project.snapshot.sync",
        version="v1",
        result={
            "project_id": 3,
            "status": "identity_only",
            "snapshot_id": None,
            "snapshots": [
                {
                    "status": "identity_only",
                    "ref": "HEAD",
                    "commit_sha": commit_sha,
                    "snapshot_id": None,
                }
            ],
            "warnings": [],
        },
    )
    with _force_https_chunking(), _https_connection():
        rc, out, err = run_cli(
            "project",
            "snapshot",
            "sync",
            str(repo),
            "--project",
            "demo",
            "--head-only",
            "--hook",
            responses=[begin_identity_only],
        )
    assert rc == 0
    assert out == ""
    assert non_progress_err(err) == ""
    assert [call["payload"]["operation"] for call in CALLS] == ["begin"]
    assert CALLS[0]["payload"]["snapshot"]["contents_included"] is False


def test_hook_mode_payload_too_large_defers_cold_upload(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    success = FunctionCallResponse(
        success=True,
        function="project.snapshot.sync",
        version="v1",
        result={},
    )
    with _force_https_chunking(), _https_connection():
        rc, out, err = run_cli(
            "project",
            "snapshot",
            "sync",
            str(repo),
            "--project",
            "demo",
            "--head-only",
            "--hook",
            responses=[success, success],
        )
    assert rc == 0
    assert out == ""
    # A deferral now reads as a calm note, not a scary "FAILED ... repair".
    assert "note:" in err
    assert "deferred" in err
    assert "snapshot sync failed" not in err
    assert "yoke project snapshot sync" in err
    assert [call["payload"]["operation"] for call in CALLS] == [
        "begin",
        "abort",
    ]
