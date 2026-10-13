"""Target-root, hook-script, service-client, and Yoke-target gating.

Owns the resolution chain that decides which workspace the hook is
running against, the matching ``service_client.py`` path, and the
``is_yoke_target`` predicate that gates orientation rendering. Kept
separate from event/registration plumbing so callers that only need
target identification do not pull in subprocess / event helpers.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Optional


def resolve_target_root(script_dir: str = "") -> str:
    """Resolve the target repo root whose state the hook should inspect."""
    repo_root = os.environ.get("YOKE_REPO_ROOT", "")
    if repo_root and os.path.isdir(repo_root):
        return repo_root

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if project_dir:
        return project_dir

    if script_dir:
        try:
            candidate = str(Path(script_dir).resolve().parents[3])
        except IndexError:
            candidate = ""
        if candidate:
            return candidate

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return ""


def _str_or(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _git_toplevel(cwd: Optional[str]) -> str:
    if not cwd:
        return ""
    try:
        root = Path(cwd).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return ""
    if not root.is_dir():
        return ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _env_target_root() -> str:
    for key in (
        "YOKE_TARGET_REPO_ROOT",
        "YOKE_REPO_ROOT",
        "CLAUDE_PROJECT_DIR",
        "CODEX_PROJECT_DIR",
        "YOKE_ROOT",
    ):
        root = os.environ.get(key, "")
        if root and os.path.isdir(root):
            return root
    return ""


def resolve_context_target_root(
    payload: dict[str, Any], cwd: Optional[str]
) -> Optional[str]:
    """Resolve the repo root to store on a ``HookContext`` for policy lookups."""
    for key in ("target_root", "project_dir"):
        value = _str_or(payload.get(key))
        if value:
            return value
    if cwd:
        root = _git_toplevel(cwd)
        return root or cwd
    root = _env_target_root()
    return root or None


def resolve_hook_script_dir() -> str:
    """Resolve the hook script directory for sibling helpers."""
    from yoke_core.hooks.service_client import resolve_repo_root

    script_dir = os.environ.get("YOKE_SCRIPT_DIR", "")
    if script_dir:
        return script_dir
    return str(Path(resolve_repo_root()) / ".agents" / "skills" / "yoke" / "scripts")


def target_service_client_path(target_root: str) -> str:
    """Return the service_client.py path that can register target sessions.

    Yoke checkouts carry ``runtime/api/service_client.py`` themselves.
    External managed projects do not, so their hooks must call
    the installed Yoke code root while still passing the external workspace
    as the target authority.
    """
    candidate = os.path.join(target_root, "runtime", "api", "service_client.py")
    if os.path.isfile(candidate):
        return candidate
    from yoke_core.hooks.service_client import resolve_repo_root

    return os.path.join(resolve_repo_root(), "runtime", "api", "service_client.py")


def is_yoke_target(root: str, db_path: str) -> bool:
    """Return True when the hook is running inside a Yoke-managed workspace."""
    from yoke_contracts.hook_runner.project_scope import project_id_for_root

    return project_id_for_root(root) is not None


__all__ = [
    "is_yoke_target",
    "resolve_context_target_root",
    "resolve_hook_script_dir",
    "resolve_target_root",
    "target_service_client_path",
]
