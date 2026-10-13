"""Resolve hook project membership from the executing machine's checkout map."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yoke_contracts.machine_config import runtime as machine_config
from yoke_contracts.machine_config.checkout import main_checkout
from yoke_contracts.machine_config.schema_projects import (
    mapped_checkouts,
    project_entry_for_checkout,
)


def workspace_path_candidates(payload: dict[str, Any]) -> list[str]:
    """Read harness workspace facts in their shared precedence order."""
    roots = payload.get("workspace_roots")
    candidates = (
        [r for r in roots if isinstance(r, str) and r.strip()]
        if isinstance(roots, list)
        else []
    )
    for key in ("cwd", "workspace", "project_dir"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value)
    return candidates


def project_id_for_root(root: str | Path) -> int | None:
    """Find a registered checkout, never a connection or a parent Git repo."""
    if not root or not machine_config.config_path().is_file():
        return None
    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        return None
    config = machine_config.load_config()
    primary = main_checkout(path)
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        # A nested independent repository must not inherit the outer mapping.
        config = {
            "projects": [
                {"checkout": checkout, "project_id": project_id}
                for checkout, project_id in mapped_checkouts(config)
                if Path(checkout).expanduser().resolve() == primary
            ]
        }
    return project_entry_for_checkout(config, primary).get("project_id")


def project_id_for_payload(payload: dict[str, Any]) -> int | None:
    """Classify the actual command directory before the session workspace."""
    for source in (
        payload.get("tool_input"),
        payload.get("toolInput"),
        payload.get("input"),
        payload,
    ):
        if isinstance(source, dict):
            for key in ("workdir", "working_directory"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return project_id_for_root(value)
    for value in workspace_path_candidates(payload):
        project_id = project_id_for_root(value)
        if project_id is not None:
            return project_id
    return None
