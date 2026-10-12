"""Disposable checkout and manifest builders for source refresh tests."""

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git_init(root: Path) -> None:
    root.mkdir(parents=True)
    subprocess.run(
        ["git", "-C", str(root), "init", "-q"],
        capture_output=True,
        text=True,
        check=True,
    )


def _project_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _seed_manifest(
    root: Path,
    project_id: int,
    project_slug: str = "external-project",
) -> None:
    path = root / ".yoke/install-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "manifest_schema": 1,
                "yoke_version": "packaged-baseline",
                "project_id": project_id,
                "project_slug": project_slug,
                "mode": "copy",
                "files": {},
                "contract_files": {},
                "strategy_files": {},
                "created_settings_files": [],
                "hook_entries": {},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
