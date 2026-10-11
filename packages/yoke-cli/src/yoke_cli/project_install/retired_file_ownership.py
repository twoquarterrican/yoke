"""Prove installer retirements absent from the current manifest territory."""

from pathlib import Path

from yoke_cli.project_install import checkout_gate
from yoke_cli.project_install import publication_commit_parent as parent_read
from yoke_cli.project_install.files import sha256_text
from yoke_cli.project_install.install_recovery import GitOwnership
from yoke_cli.project_install.instruction_discovery import RETIRED_INSTRUCTION_PATHS
from yoke_cli.project_install.released_bundle_files import ReleasedBundleFiles
from yoke_contracts.project_contract.managed_block import block_span


def proves_retirement(root: Path, sha: str, rel: str) -> bool:
    """Only known installed bytes may disappear; instruction user text stays."""
    listed = checkout_gate.run_git(root, "ls-tree", "--name-only", sha, "--", rel)
    if listed.returncode:
        return False
    before, state = parent_read.parent_text(root, sha, rel)
    if state != parent_read.PRESENT:
        return False
    if rel in RETIRED_INSTRUCTION_PATHS:
        span = block_span(before)
        if not span:
            return False
        after, read = (
            parent_read.blob(root, f"{sha}:{rel}")
            if listed.stdout.strip()
            else ("", True)
        )
        remainder = before[: span[0]] + before[span[1] :]
        return read and after.strip() == remainder.strip()
    if listed.stdout.strip():
        return False  # This proof permits removal only, never a new arbitrary body.
    if not rel.startswith(
        (
            ".agents/skills/yoke/",
            ".claude/skills/yoke/",
            ".codex/skills/yoke/",
            ".cursor/skills/yoke/",
            ".yoke/docs/",
            ".claude/agents/",
            ".codex/agents/",
            ".cursor/agents/",
        )
    ):
        return False
    parents, read = parent_read.recorded_parents(root, sha)
    return bool(
        read
        and parents
        and (
            ReleasedBundleFiles().proves(rel, before)
            or GitOwnership(root, revision=parents[0]).proves(rel, sha256_text(before))
        )
    )
