"""Resolve linked Git checkouts independently of their directory layout."""

from pathlib import Path
import subprocess

from yoke_contracts.machine_config.schema_connections import MachineConfigContractError


def main_checkout(root: str | Path) -> Path:
    """Return Git's primary checkout, or the supplied root outside Git."""
    root = Path(root).expanduser().resolve()
    if not any((parent / ".git").exists() for parent in (root, *root.parents)):
        return root
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain", "-z"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _identity_refusal(root) from exc
    if result.returncode == 0:
        first = result.stdout.split("\0\0", 1)[0].split("\0")
        if first and first[0].startswith("worktree ") and "bare" not in first:
            return Path(first[0][9:]).resolve()
    raise _identity_refusal(root)


def _identity_refusal(root: Path) -> MachineConfigContractError:
    return MachineConfigContractError(
        f"checkout_identity_unavailable: cannot resolve Git's main checkout for {root}; "
        "repair Git access until git worktree list --porcelain succeeds there, then rerun the command"
    )
