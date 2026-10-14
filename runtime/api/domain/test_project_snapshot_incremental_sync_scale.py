"""A claim-widen snapshot sync on an ~18k-file repo takes seconds.

The integration target's snapshot is already stored, as it is for any lane
of a project that synced before. The lane's sync then reads and uploads
only the files its own commit changed, while the server assembles the
complete 18k-file snapshot from the stored base.
"""

from __future__ import annotations

import io
import time
from pathlib import Path

from runtime.api.domain._incremental_snapshot_test_helpers import (
    appended_paths,
    git,
    in_process_handler,
    init_repo,
)
from runtime.api.domain._path_snapshots_test_helpers import path_snapshot_db
from yoke_cli.commands.adapters.project_snapshot import (
    sync_local_snapshot_for_write,
)
from yoke_core.domain.path_snapshot_content_rows import find_content_snapshot_id

FILE_COUNT = 18_000
CHANGED = [f"pkg{index}/mod0.py" for index in range(5)]
#: Generous against shared CI hosts; the sync measures about a second
#: locally, against tens of seconds for a full scan and upload.
SYNC_BUDGET_SECONDS = 10.0


def _fast_import(repo: Path) -> None:
    """Commit FILE_COUNT small modules on main, then a 5-file lane commit."""
    lines = []
    for mark, (branch, paths, body) in enumerate(
        [
            (
                "main",
                [f"pkg{i // 100}/mod{i % 100}.py" for i in range(FILE_COUNT)],
                b"",
            ),
            ("lane", CHANGED, b"VALUE = 2\n"),
        ],
        start=1,
    ):
        lines.append(f"commit refs/heads/{branch}".encode())
        lines.append(f"mark :{mark}".encode())
        lines.append(
            f"committer Test <t@example.com> {1_700_000_000 + mark} +0000".encode()
        )
        lines.append(b"data 4\nseed")
        if mark == 2:
            lines.append(b"from :1")
        for path in paths:
            data = body or f"import os\nNAME = {path!r}\n".encode()
            lines.append(f"M 100644 inline {path}".encode())
            lines.append(b"data %d" % len(data))
            lines.append(data)
        lines.append(b"")
    git(repo, "fast-import", "--quiet", stdin=b"\n".join(lines) + b"\n")


def test_widen_sync_of_18k_file_lane_takes_seconds(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    init_repo(repo)
    _fast_import(repo)
    git(repo, "checkout", "-q", "-f", "main")
    with path_snapshot_db(tmp_path, repo) as conn:
        with in_process_handler(monkeypatch):
            seeded = sync_local_snapshot_for_write(
                project="demo",
                repo_root=str(repo),
                integration_target="main",
                session_id=None,
                timeout_s=None,
                stderr=io.StringIO(),
            )
        assert seeded["status"] == "ok", seeded
        git(repo, "checkout", "-q", "lane")
        lane_head = git(repo, "rev-parse", "HEAD")

        with in_process_handler(monkeypatch) as calls:
            started = time.monotonic()
            status = sync_local_snapshot_for_write(
                project="demo",
                repo_root=str(repo),
                integration_target="main",
                session_id=None,
                timeout_s=None,
                stderr=io.StringIO(),
            )
            elapsed = time.monotonic() - started

        assert status["status"] == "ok", status
        assert appended_paths(calls) == sorted(CHANGED)
        assert find_content_snapshot_id(conn, 3, lane_head) is not None
        stored = conn.execute(
            "SELECT COUNT(*) FROM path_snapshot_entries e "
            "JOIN path_snapshots s ON s.id = e.snapshot_id "
            "JOIN path_targets t ON t.id = e.target_id "
            "WHERE s.commit_sha = '" + lane_head + "' AND t.kind = 'file'"
        ).fetchone()[0]
        assert stored == FILE_COUNT
    print(f"incremental widen sync of {FILE_COUNT} files: {elapsed:.2f}s")
    assert elapsed < SYNC_BUDGET_SECONDS
