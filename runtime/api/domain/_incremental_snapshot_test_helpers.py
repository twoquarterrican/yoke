"""Drive the real snapshot-sync client against the real handler in-process."""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import pytest

from yoke_contracts.api.function_call import (
    ActorContext,
    FunctionCallRequest,
    FunctionCallResponse,
)
from yoke_core.domain import db_backend
from yoke_core.domain.handlers import project_snapshot_sync as handler


def git(repo: Path, *args: str, stdin: bytes | None = None) -> str:
    return (
        subprocess.run(
            ["git", "-C", str(repo), *args],
            input=stdin,
            capture_output=True,
            check=True,
        )
        .stdout.decode("utf-8")
        .strip()
    )


def init_repo(repo: Path) -> None:
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "core.hooksPath", "/dev/null")


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@contextmanager
def in_process_handler(monkeypatch: pytest.MonkeyPatch) -> Iterator[List[dict]]:
    """Route every chunked sync call to the handler; yield the payloads."""
    calls: List[dict] = []

    def bridge(**kwargs: Any) -> FunctionCallResponse:
        calls.append(kwargs["payload"])
        outcome = handler.handle_project_snapshot_sync(
            FunctionCallRequest(
                function=kwargs["function_id"],
                actor=ActorContext(session_id="test-session"),
                target=kwargs["target"],
                payload=kwargs["payload"],
            )
        )
        return FunctionCallResponse(
            success=outcome.primary_success,
            function=kwargs["function_id"],
            version="v1",
            result=outcome.result_payload or {},
            error=outcome.error,
        )

    chunked = "yoke_cli.commands.adapters.project_snapshot_chunked"
    monkeypatch.setattr(f"{chunked}.call_dispatcher", bridge)
    monkeypatch.setattr(f"{chunked}.ensure_handlers_loaded", lambda: None)
    # Lane-head binding needs the item tables this path-only schema lacks;
    # it is independent of which snapshot the upload stores.
    monkeypatch.setattr(
        "yoke_core.domain.item_worktree_head.record_head_for_checkout",
        lambda *_args, **_kwargs: None,
    )
    yield calls


def stored_snapshot(conn: Any, commit_sha: str) -> Dict[str, List[Tuple]]:
    """Everything the server stores for one commit, keyed by path."""
    p = "%s" if db_backend.connection_is_postgres(conn) else "?"
    entries = conn.execute(
        "SELECT t.path_string, t.kind, e.line_count, e.language, "
        "e.module_name, e.area, e.is_generated, e.dependency_edges "
        "FROM path_snapshot_entries e "
        "JOIN path_targets t ON t.id = e.target_id "
        "JOIN path_snapshots s ON s.id = e.snapshot_id "
        f"WHERE s.commit_sha = {p}",
        (commit_sha,),
    ).fetchall()
    symlinks = conn.execute(
        "SELECT f.symlink_path, f.reason, f.target_attempt, f.canonical_path "
        "FROM path_snapshot_symlink_facts f "
        "JOIN path_snapshots s ON s.id = f.snapshot_id "
        f"WHERE s.commit_sha = {p}",
        (commit_sha,),
    ).fetchall()
    return {
        "entries": sorted(
            (*tuple(row)[:7], json.loads(tuple(row)[7] or "[]")) for row in entries
        ),
        "symlinks": sorted(tuple(row) for row in symlinks),
    }


def appended_paths(calls: List[dict]) -> List[str]:
    return sorted(
        entry["path"]
        for call in calls
        if call.get("operation") == "append"
        for entry in call["files"]
    )


__all__ = [
    "appended_paths",
    "commit_all",
    "git",
    "in_process_handler",
    "init_repo",
    "stored_snapshot",
]
