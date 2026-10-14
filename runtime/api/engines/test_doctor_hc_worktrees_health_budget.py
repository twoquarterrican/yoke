"""HC-worktree-health retires many landed lanes inside its check budget.

A machine holding dozens of landed lanes used to spend the whole budget on one
control-plane verdict and one target fetch per lane, then abort before pruning
any. These tests drive real git lanes through the check under the real budget:
one batched verdict read, one fetch per target, and each lane retired as soon
as it is proved, so an aborted run keeps what it already retired.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, List, Tuple
from unittest.mock import patch

import pytest

from yoke_contracts.doctor_budget import DoctorBudgetExhausted, check_budget
from yoke_core.engines import doctor_hc_worktrees_health as hc
from yoke_core.engines import doctor_worktree_lane_authority as lane_authority
from yoke_core.engines import doctor_worktree_terminal_lanes as terminal_lanes
from yoke_core.engines.doctor_https_compose import UnavailableControlPlane
from yoke_core.engines.doctor_report import DoctorArgs, RecordCollector

LANES = 50


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def _lane_branches(repo: Path) -> set[str]:
    refs = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/YOK-*")
    return set(refs.split())


@pytest.fixture
def landed_lanes(tmp_path: Path, monkeypatch) -> Tuple[Path, List[Path]]:
    """A checkout with an origin and LANES clean lanes already on main."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "--initial-branch=main", str(origin)],
        check=True,
        capture_output=True,
    )
    repo = tmp_path / "repo"
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(repo)],
        check=True,
        capture_output=True,
    )
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "commit", "-m", "base")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "origin", "main")
    lanes = []
    for i in range(LANES):
        lane = repo / ".worktrees" / f"YOK-{i}"
        _git(repo, "worktree", "add", "-b", f"YOK-{i}", str(lane), "main")
        lanes.append(lane)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(hc._base, "_resolve_repo_root", lambda: str(repo))
    # The terminal transaction already released each lane row.
    monkeypatch.setattr(
        "yoke_core.engines.merge_landed_lane_cleanup.release_lane_row",
        lambda *_a, **_kw: None,
    )
    return repo, lanes


@pytest.fixture
def relay_calls(landed_lanes, monkeypatch) -> List[Tuple[str, dict]]:
    """Serve the inventory and an idle authority verdict for every lane."""
    _repo, lanes = landed_lanes
    calls: List[Tuple[str, dict]] = []
    rows = [
        {
            "item_id": i,
            "public_ref": lane.name,
            "status": "done",
            "branch": lane.name,
            "path": str(lane),
            "state": "released",
            "target_branch": "main",
        }
        for i, lane in enumerate(lanes)
    ]

    def relay(function_id: str, payload: dict, *_a: Any, **_kw: Any) -> dict:
        calls.append((function_id, payload))
        if function_id == "item_worktrees.inventory":
            return {"lanes": rows}
        if function_id == "merge.prune.authority_verdicts":
            verdict = {"prunable": True, "reason": "prunable"}
            return {"verdicts": [verdict] * len(payload["lanes"])}
        raise AssertionError(f"unexpected relayed function {function_id}")

    monkeypatch.setattr(lane_authority, "relay", relay)
    return calls


def _fix_within_budget() -> RecordCollector:
    rec = RecordCollector()
    with check_budget():
        hc.hc_worktree_health(
            UnavailableControlPlane(), DoctorArgs(project="yoke", fix=True), rec
        )
    return rec


def test_fifty_landed_lanes_retire_with_one_verdict_read_and_one_fetch(
    landed_lanes, relay_calls
):
    repo, lanes = landed_lanes
    git_commands: List[List[str]] = []
    real_run = hc._base._run

    def run(cmd, *args, **kwargs):
        git_commands.append(cmd)
        return real_run(cmd, *args, **kwargs)

    with patch.object(hc._base, "_run", run):
        rec = _fix_within_budget()

    [result] = rec.results
    assert result.result == "PASS", result.detail
    assert result.detail.count("Fixed: removed terminal lane") == LANES
    assert not any(lane.exists() for lane in lanes)
    assert _lane_branches(repo) == set()
    verdict_reads = [
        payload
        for function_id, payload in relay_calls
        if function_id == "merge.prune.authority_verdicts"
    ]
    assert len(verdict_reads) == 1
    assert len(verdict_reads[0]["lanes"]) == LANES
    fetches = [cmd for cmd in git_commands if "fetch" in cmd]
    assert fetches == [["git", "-C", str(repo), "fetch", "origin", "main"]]


def test_a_run_the_budget_aborts_keeps_the_lanes_it_already_retired(
    landed_lanes, relay_calls, monkeypatch
):
    repo, lanes = landed_lanes
    retired_before_abort = 3
    real_prune = terminal_lanes.prune_landed_lane
    prunes: List[str] = []

    def prune_until_the_budget_runs_out(**kwargs):
        if len(prunes) == retired_before_abort:
            raise DoctorBudgetExhausted("doctor_check_budget_exhausted")
        prunes.append(kwargs["branch"])
        return real_prune(**kwargs)

    monkeypatch.setattr(
        terminal_lanes, "prune_landed_lane", prune_until_the_budget_runs_out
    )

    with pytest.raises(DoctorBudgetExhausted):
        _fix_within_budget()

    retired = [lane for lane in lanes if not lane.exists()]
    assert [lane.name for lane in retired] == prunes
    assert len(retired) == retired_before_abort
    assert _lane_branches(repo) == {lane.name for lane in lanes} - set(prunes)
