"""A deployment run's member close-out retires the member's lanes.

Run settlement closes members without a session, so terminal lane cleanup
reads the closed item itself: its project names this machine's checkout and
target branch, and its lane rows name what to retire. A lane cleanup could
not retire is printed on the run's output with the recovery that frees it,
and never holds the run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from runtime.api.domain.test_run_success_member_settlement import _run
from runtime.api.domain.test_shared_gate_two_phase_settlement import (
    MEMBERS,
    _executing_run,
    _five_ready_members,
)
from runtime.api.domain.test_status_transition_preflight import (
    _isolate_status_effects,
)
from yoke_core.domain import terminal_lane_cleanup
from yoke_core.domain.deployment_runs_crud_mutate import cmd_update
from yoke_core.domain.item_worktrees import record_item_worktree
from yoke_core.domain.project_identity import render_item_ref
from yoke_core.domain.workflow_behavior import LANE_IMPLEMENTATION
from yoke_core.domain.worktree_capacity import DOCTOR_RETIRE_RECIPE
from yoke_core.engines.merge_worktree_safe_prune import WorktreeSweep


def _member_lanes(conn: Any, checkout: Path) -> dict[str, int]:
    lanes: dict[str, int] = {}
    for item_id in MEMBERS:
        branch = f"lane-{item_id}"
        path = checkout / ".worktrees" / branch
        path.mkdir(parents=True)
        record_item_worktree(
            conn,
            item_id=item_id,
            branch=branch,
            path=str(path),
            lane_role=LANE_IMPLEMENTATION,
            validate_policy=False,
        )
        lanes[branch] = item_id
    conn.commit()
    return lanes


def _wire_cleanup(
    monkeypatch, checkout: Path, *, preserved: tuple[str, ...] = ()
) -> dict[str, list[Any]]:
    """Run the real cleanup against *checkout*, recording the git-side calls."""
    calls: dict[str, list[Any]] = {"pruned": [], "swept": []}
    real_cleanup = terminal_lane_cleanup.cleanup_terminal_item_lanes

    def _prune(*, branch: str, target: str, **_kw) -> tuple[str, ...]:
        calls["pruned"].append((branch, target))
        return preserved

    def _sweep(*, repo_root: str, target: str, **_kw) -> WorktreeSweep:
        calls["swept"].append((repo_root, target))
        return WorktreeSweep()

    def _cleanup(item, **kwargs):
        return real_cleanup(item, **kwargs, prune=_prune, sweep=_sweep)

    monkeypatch.setattr(
        terminal_lane_cleanup,
        "checkout_for_project_id",
        lambda project_id: checkout if project_id is not None else None,
    )
    monkeypatch.setattr(terminal_lane_cleanup, "cleanup_terminal_item_lanes", _cleanup)
    return calls


def test_run_close_out_retires_each_member_lane_and_sweeps(
    test_db: Any, monkeypatch, tmp_path: Path
) -> None:
    _isolate_status_effects(monkeypatch)
    _five_ready_members(test_db)
    lanes = _member_lanes(test_db, tmp_path)
    _executing_run(test_db, "run-lane-cleanup")
    calls = _wire_cleanup(monkeypatch, tmp_path)

    assert cmd_update("run-lane-cleanup", "status", "succeeded") is None

    assert _run(test_db, "run-lane-cleanup") == ("succeeded", True)
    assert sorted(calls["pruned"]) == sorted((branch, "main") for branch in lanes)
    assert calls["swept"] == [(str(tmp_path.resolve()), "main")] * len(MEMBERS)


def test_a_preserved_lane_is_printed_on_the_run_output(
    test_db: Any, monkeypatch, tmp_path: Path, capsys
) -> None:
    _isolate_status_effects(monkeypatch)
    _five_ready_members(test_db)
    _member_lanes(test_db, tmp_path)
    _executing_run(test_db, "run-lane-kept")
    _wire_cleanup(monkeypatch, tmp_path, preserved=("worktree has local changes",))

    assert cmd_update("run-lane-kept", "status", "succeeded") is None

    output = capsys.readouterr().out
    assert _run(test_db, "run-lane-kept") == ("succeeded", True)
    for item_id in MEMBERS:
        ref = render_item_ref(test_db, item_id)
        assert (
            f"Lane cleanup warning: {ref} at "
            f"{tmp_path / '.worktrees' / f'lane-{item_id}'}: "
            "worktree has local changes"
        ) in output
    assert DOCTOR_RETIRE_RECIPE in output


def test_a_machine_without_the_checkout_says_so_on_the_run_output(
    test_db: Any, monkeypatch, tmp_path: Path, capsys
) -> None:
    _isolate_status_effects(monkeypatch)
    _five_ready_members(test_db)
    _member_lanes(test_db, tmp_path)
    _executing_run(test_db, "run-no-checkout")
    monkeypatch.setattr(
        terminal_lane_cleanup, "checkout_for_project_id", lambda _project_id: None
    )

    assert cmd_update("run-no-checkout", "status", "succeeded") is None

    output = capsys.readouterr().out
    assert _run(test_db, "run-no-checkout") == ("succeeded", True)
    ref = render_item_ref(test_db, MEMBERS[0])
    assert (
        f"Lane cleanup warning: {ref}: terminal lane cleanup preserved: "
        "checkout unavailable"
    ) in output
    assert DOCTOR_RETIRE_RECIPE in output
