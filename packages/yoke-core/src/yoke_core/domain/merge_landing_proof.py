"""Require fresh Git ancestry before recording a landing."""

from __future__ import annotations

import subprocess

from yoke_cli.config import repo_upstream_git as upstream
from yoke_core.domain import standalone_item_merge_git as git


class LandingUnverified(RuntimeError):
    """A landing has no fresh proof; its lane and lifecycle must be retained."""


def verified_target_sha(repo_root: str, target: str, candidate: str) -> str:
    """Prove a landing, turning unreadable Git into a recoverable refusal."""
    try:
        return _verified_target_sha(repo_root, target, candidate)
    except (OSError, subprocess.SubprocessError) as exc:
        raise LandingUnverified(
            f"merge_landing_git_failed: {exc}. Preserve the lane and pre-landing "
            "stage; repair checkout access and re-run the governed merge command."
        ) from exc


def _verified_target_sha(repo_root: str, target: str, candidate: str) -> str:
    """Fetch the tracked remote target and prove it contains the candidate.

    A repository with no remote proves its local target instead. Remote
    failures never fall back to local refs, cached receipts, or push exit codes.
    """
    recovery = (
        "Keep the item in its pre-landing stage and preserve the lane. "
        "Repair checkout routing or remote access, publish the candidate through "
        "the governed merge command, then re-run that same command."
    )

    def refuse(reason: str, detail: str) -> None:
        raise LandingUnverified(f"{reason}: {detail}. {recovery}")

    if not repo_root or not target or not candidate:
        refuse(
            "merge_landing_identity_missing",
            "checkout, target and candidate are required",
        )
    remotes = git._git(repo_root, "remote")
    if remotes.returncode:
        refuse("merge_landing_remote_unreadable", remotes.stderr.strip())
    ref = target
    if remotes.stdout.strip():
        remote, _ = upstream.resolve_remote(repo_root, target)
        if remote == "." or remote not in remotes.stdout.splitlines():
            refuse(
                "merge_landing_remote_unconfigured",
                f"no remote tracks {target} in {repo_root}",
            )
        ref = f"refs/remotes/{remote}/{target}"
        try:
            fetched = upstream.fetch_branch(repo_root, remote, target)
        except (OSError, subprocess.SubprocessError) as exc:
            refuse("merge_landing_fetch_failed", str(exc))
        if fetched.returncode:
            refuse(
                "merge_landing_fetch_failed",
                fetched.stderr.strip() or fetched.stdout.strip(),
            )
    sha = git.git_out(repo_root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if not sha:
        refuse(
            "merge_landing_target_unreadable", f"cannot resolve {ref} in {repo_root}"
        )
    contains, error = git.ancestry(repo_root, candidate, sha)
    if contains is None:
        refuse("merge_landing_ancestry_unreadable", error)
    if not contains:
        refuse(
            "merge_candidate_not_landed",
            f"{ref} at {sha} does not contain candidate {candidate} in {repo_root}",
        )
    return sha
