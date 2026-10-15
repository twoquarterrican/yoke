"""Local (non-GitHub) epic task sync operations.

Contains operations that write only to the local DB without making any
GitHub API calls. Currently: dispatch-chain generation.
"""

from __future__ import annotations

import json
from typing import Any, TextIO

from yoke_contracts.timestamps import utc_now
from yoke_core.domain.db_helpers import instant_parameter

from yoke_core.domain import db_backend, project_settings
from yoke_core.domain.epic_task_sync import _placeholder, _repo_root
from yoke_core.domain.worktree_naming import worktree_name_for_item
from yoke_core.domain.item_worktrees import record_worker_item_worktree


def load_task_rows(conn: Any, *, placeholder: str, epic_name: str):
    """Load the durable task state needed to create or link issues."""
    return conn.execute(
        f"""
        SELECT t.id, t.epic_id, t.task_num, COALESCE(t.title, ''),
               COALESCE(iw.branch, ''), COALESCE(t.context_estimate, ''),
               COALESCE(t.dependencies, ''), COALESCE(t.status, ''),
               COALESCE(t.dispatch_attempts, 0)
        FROM epic_tasks t LEFT JOIN item_worktrees iw ON iw.id=t.item_worktree_id
        WHERE t.epic_id = {placeholder}
        ORDER BY t.task_num ASC
        """,
        (epic_name,),
    ).fetchall()


def _generate_dispatch_chains(
    *,
    epic_name: str,
    worktree_map: list[tuple[str, str]],
    repo_root: str,
    conn: Any,
    stdout: TextIO,
) -> None:
    """Generate dispatch chains in the DB for each unique worktree branch."""
    if not worktree_map:
        return

    max_attempts = project_settings.get_project_int(repo_root, "max_attempts")
    worktrees_dir = project_settings.get_project_str(repo_root, "worktrees_dir")

    # Get unique worktree branches in order
    seen: set[str] = set()
    unique_branches: list[str] = []
    for wt_branch, _ in worktree_map:
        if wt_branch not in seen:
            seen.add(wt_branch)
            unique_branches.append(wt_branch)

    for wt_branch in unique_branches:
        p = _placeholder(conn)
        wt_slug = wt_branch.replace("/", "-")
        chain_path = f"{repo_root}/{worktrees_dir}/{wt_slug}"
        # Check if chain already exists
        lane_row = conn.execute(
            f"SELECT id, path FROM item_worktrees WHERE item_id={p} "
            f"AND branch={p} AND state='active'",
            (int(epic_name), wt_branch),
        ).fetchone()
        if lane_row is not None and lane_row[1]:
            lane_id = int(lane_row[0])
        else:
            lane_id = int(
                record_worker_item_worktree(
                    conn,
                    item_id=int(epic_name),
                    branch=wt_branch,
                    path=chain_path,
                )["id"]
            )
        existing = conn.execute(
            f"SELECT id FROM epic_dispatch_chains WHERE epic_id = {p} AND item_worktree_id = {p}",
            (epic_name, lane_id),
        ).fetchone()
        if existing:
            print(
                f"Dispatch chain already exists: {epic_name}/{wt_branch}", file=stdout
            )
            continue

        # Collect task IDs for this worktree
        task_nums = [tn for wb, tn in worktree_map if wb == wt_branch]
        timestamp = instant_parameter(conn, utc_now())
        queue_json = json.dumps(task_nums)
        first_task = task_nums[0] if task_nums else ""

        conn.execute(
            f"""INSERT INTO epic_dispatch_chains
               (epic_id, item_worktree_id, queue,
                current_index, current_task, current_attempt,
                max_attempts, no_chain, started_at, last_updated)
               VALUES ({p}, {p}, {p}, 0, {p}, 0, {p}, 0, NULL, {p})""",
            (
                epic_name,
                lane_id,
                queue_json,
                first_task,
                max_attempts,
                timestamp,
            ),
        )
        conn.commit()

        task_count = len(task_nums)
        print(
            f"Generated dispatch chain: {epic_name}/{wt_branch} ({task_count} tasks)",
            file=stdout,
        )


def prepare_dispatch_chains(
    conn: Any,
    *,
    epic_name: str,
    stdout: TextIO,
    stderr: TextIO,
) -> bool:
    """Materialize local queues before optional issue publication."""
    rows = load_task_rows(conn, placeholder=_placeholder(conn), epic_name=epic_name)
    if not rows:
        return True
    try:
        repo_root = str(_repo_root())
    except (RuntimeError, FileNotFoundError) as exc:
        print(
            f"Error: dispatch_checkout_unavailable: {exc}. "
            "Restore the project checkout and retry yoke items github-sync.",
            file=stderr,
        )
        return False
    worktree_map = []
    for row in rows:
        task_num, branch = int(row[2]), str(row[4] or "")
        if not branch:
            branch = worktree_name_for_item(conn, int(epic_name))
            print(
                f"Warning: task {task_num:03d} has empty worktree, defaulting to {branch}",
                file=stderr,
            )
            lane = record_worker_item_worktree(
                conn,
                item_id=int(epic_name),
                branch=branch,
                path=None,
            )
            p = _placeholder(conn)
            conn.execute(
                f"UPDATE epic_tasks SET item_worktree_id={p} WHERE epic_id={p} AND task_num={p}",
                (int(lane["id"]), epic_name, task_num),
            )
        worktree_map.append((branch, f"{task_num:03d}"))
    try:
        _generate_dispatch_chains(
            epic_name=epic_name,
            worktree_map=worktree_map,
            repo_root=repo_root,
            conn=conn,
            stdout=stdout,
        )
    except (*db_backend.operational_error_types(conn), ValueError) as exc:
        conn.rollback()
        print(
            f"Error: dispatch_chain_generation_failed: {exc}. "
            "Repair the named lane/database condition and retry yoke items github-sync.",
            file=stderr,
        )
        return False
    return True
