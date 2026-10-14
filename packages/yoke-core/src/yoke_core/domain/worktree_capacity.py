"""What frees a checkout that reached its worktree cap.

``max_active_worktrees`` counts every managed worktree in a checkout. When a
new lane would exceed it, lane creation first runs the merged-lane sweep —
the one cleanup boundary that always runs on the lanes' own machine — and
then refuses for what remains, naming each kind of slot with the recovery
that frees it.
"""

from __future__ import annotations

import sys
from typing import Any, List, Sequence

from yoke_core.engines.branch_landed_evidence import assess_branch_landed
from yoke_core.engines.deploy_run_worktree_naming import DRIVER_WORKTREE_PREFIX
from yoke_core.engines.deploy_run_worktree_retirement import (
    assess_deploy_run_worktrees,
)
from yoke_core.engines.git_worktree_registry import registered_worktrees

# The resolvable invocation, not the shorthand: a reader copies this out of a
# refusal, so `yoke doctor --fix` — which routes nowhere — would strand them.
DOCTOR_RETIRE_RECIPE = "yoke watch doctor -- --only HC-worktree-health --fix"


def _git(args: List[str], *, cwd: str, capture: bool = True) -> Any:
    from yoke_core.engines._merge_worktree_runtime import _run_git

    return _run_git(args, cwd=cwd, capture=capture)


def _landed_item_lanes(
    repo_root: str, item_lanes: Sequence[str], landed_base: str
) -> set[str]:
    """The item lanes whose branch ``landed_base`` already carries.

    Merging such a lane frees nothing: the slot frees when the lane is
    retired. A lane whose branch git cannot name stays with the unmerged.
    """
    if not landed_base:
        return set()
    branches = {
        entry.path.name: entry.branch
        for entry in registered_worktrees(_git, repo_root) or ()
    }
    landed: set[str] = set()
    for name in item_lanes:
        branch = branches.get(name)
        if (
            branch
            and assess_branch_landed(
                lambda command: _git(command, cwd=repo_root),
                branch=branch,
                base=landed_base,
            ).landed
        ):
            landed.add(name)
    return landed


def capacity_recovery(
    repo_root: str, active_names: Sequence[str], landed_base: str
) -> str:
    """Name what holds the slots and the recovery that actually frees them.

    Each kind of slot is reported with the recovery that applies to it:
    unmerged item lanes merge; landed item lanes and finished runs' driver
    trees are retired by the doctor; an open run's driver tree is in use —
    its driver runs from it — and is never offered for retirement.
    """
    item_lanes = [
        name for name in active_names if not name.startswith(DRIVER_WORKTREE_PREFIX)
    ]
    driver_lanes = [
        name for name in active_names if name.startswith(DRIVER_WORKTREE_PREFIX)
    ]
    landed = _landed_item_lanes(repo_root, item_lanes, landed_base)
    unmerged = [name for name in item_lanes if name not in landed]
    open_runs = (
        {
            lane.path.name
            for lane in assess_deploy_run_worktrees(repo_root=repo_root)
            if lane.run_is_open
        }
        if driver_lanes
        else set()
    )
    in_use = [name for name in driver_lanes if name in open_runs]
    finished = [name for name in driver_lanes if name not in open_runs]
    landed_names = [name for name in item_lanes if name in landed]
    parts: List[str] = []
    if unmerged:
        parts.append(
            "Merge existing worktrees before creating more. "
            f"Item lanes: {', '.join(unmerged)}."
        )
    if landed_names:
        parts.append(
            f"{len(landed_names)} item lane(s) already landed on {landed_base}, "
            f"so no merge frees them — run `{DOCTOR_RETIRE_RECIPE}` to retire "
            "those whose items are closed; the rest free when their items "
            f"close out. Landed lanes: {', '.join(landed_names)}."
        )
    if finished:
        parts.append(
            f"{len(finished)} slot(s) are held by deploy-run driver trees, "
            f"which no merge retires — run `{DOCTOR_RETIRE_RECIPE}` to retire "
            f"the finished ones. Deploy-run lanes: {', '.join(finished)}."
        )
    if in_use:
        parts.append(
            f"{len(in_use)} slot(s) are in use by open deploy runs' drivers and "
            f"free when those runs finish. In-use deploy-run lanes: "
            f"{', '.join(in_use)}."
        )
    return " ".join(parts) if parts else "No active worktrees were reported."


def retire_finished_lanes(repo_root: str, target: str) -> None:
    """Run the merged-lane sweep before a full checkout refuses a new lane.

    A member a deployment run closes has its lanes retired on the machine that
    settles the run, and a hosted control plane settles where no lane lives.
    Lane creation always runs on the lanes' own machine, so a full checkout
    first retires what the sweep proves finished — landed lanes of closed
    items and finished runs' driver trees — then refuses for what remains.
    The sweep names everything it removed or kept on stderr.
    """
    from yoke_core.engines.merge_worktree_safe_prune import prune_managed_worktrees

    def say(message: str, **_kw: Any) -> None:
        print(message, file=sys.stderr, flush=True)

    try:
        prune_managed_worktrees(repo_root=repo_root, target=target, emit=say)
    except Exception as exc:  # noqa: BLE001 - the capacity refusal follows
        say(
            f"Merged-lane sweep stopped before lane creation: {exc}. Run "
            f"`{DOCTOR_RETIRE_RECIPE}` to retire finished lanes."
        )


__all__ = ["DOCTOR_RETIRE_RECIPE", "capacity_recovery", "retire_finished_lanes"]
