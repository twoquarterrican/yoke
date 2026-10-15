"""Retire only machine-local state proved exclusive to this installed checkout."""

from __future__ import annotations

from pathlib import Path
import subprocess
import json

from yoke_contracts.harness_folder_trust_revert import revert_folder_trust
from yoke_contracts.machine_config.checkout import main_checkout
from yoke_contracts.machine_config.schema_projects import normalize_projects
from yoke_contracts.machine_config import schema as contract
from yoke_cli.config import machine_config, machine_config_file
from yoke_cli.config.machine_config_mutation import (
    load_payload,
    serialized_mutation,
)
from yoke_cli.project_install import files

REGISTRATION_KEY = "local_registration"


def record_registration(root: Path, project_id: int, config_path) -> None:
    """Attach the exact mapping introduced by this install to its manifest."""
    manifest = files.load_manifest(root)
    manifest[REGISTRATION_KEY] = {
        "config": str(machine_config.config_path(config_path).resolve()),
        "entry": {"checkout": str(main_checkout(root)), "project_id": project_id},
    }
    files.write_manifest(root, manifest)


def cleanup(root: Path, manifest: dict, config_path) -> dict:
    """Keep independent failures reviewable without claiming complete retirement."""
    try:
        return _cleanup(root, manifest, path=config_path)
    except (
        OSError,
        ValueError,
        RuntimeError,
        TypeError,
        subprocess.SubprocessError,
    ) as exc:
        return {
            "complete": False,
            "trust": [],
            "registration": _result("failed", "local_cleanup_unavailable", str(exc)),
        }


@serialized_mutation
def _cleanup(root: Path, manifest: dict, *, path=None) -> dict:
    payload, cfg = load_payload(path)
    projects = normalize_projects(payload.get("projects"))
    reason = _shared_reason(root, projects)
    trust = revert_folder_trust(root, exclusive_reason=reason)
    record = manifest.get(REGISTRATION_KEY)
    exact = [
        entry
        for entry in payload.get("projects", [])
        if Path(entry["checkout"]).expanduser().resolve() == root
    ]
    if not exact:
        registration = _result("absent", "no_exact_registration")
    elif reason:
        registration = _result("preserved", reason)
    elif not isinstance(record, dict) or record.get("config") != str(cfg.resolve()):
        registration = _result("preserved", "registration_ownership_unknown")
    elif (
        len(exact) != 1
        or exact[0] != record.get("entry")
        or exact[0].get("project_id") != manifest.get("project_id")
    ):
        registration = _result("preserved", "registration_modified")
    elif any(row["status"] in {"failed", "preserved"} for row in trust):
        registration = _result("preserved", "trust_cleanup_unresolved")
    else:
        payload["projects"].remove(exact[0])
        errors = [
            issue.code
            for issue in contract.validate_payload(payload)
            if issue.severity == "error"
        ]
        if errors:
            raise ValueError(
                "machine_config_invalid: repair machine config before cleanup: "
                + ", ".join(errors)
            )
        # The general writer also seeds identity and strips retired keys. Here
        # only the selected project entry may change, under its existing lock.
        machine_config_file.atomic_write_text(cfg, json.dumps(payload, indent=2) + "\n")
        registration = _result("removed", "owned_exact_entry")
    return {
        "registration": registration,
        "trust": trust,
        "complete": registration["status"] in {"removed", "absent"}
        and all(row["status"] in {"removed", "absent"} for row in trust),
    }


def _shared_reason(root: Path, projects: list[dict]) -> str:
    if main_checkout(root) != root:
        return "linked_checkout_uses_main_registration"
    for entry in projects:
        other = Path(entry["checkout"]).expanduser().resolve()
        if other != root and (
            other.is_relative_to(root)
            or root.is_relative_to(other)
            or main_checkout(other) == root
        ):
            return "registration_covers_other_checkout"
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain", "-z"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode:
            return "worktree_identity_unavailable"
        members = [
            line[9:]
            for line in result.stdout.split("\0")
            if line.startswith("worktree ")
        ]
        if not members or any(Path(member).resolve() != root for member in members):
            return "registration_covers_git_worktrees"
    return ""


def _result(status: str, reason: str, detail: str = "") -> dict:
    return {
        "status": status,
        "reason": reason,
        "detail": detail,
        "recovery": "Review the exact checkout registration in machine config; resolve ownership or shared checkouts and rerun project uninstall. Preserve credentials and other project entries.",
    }
