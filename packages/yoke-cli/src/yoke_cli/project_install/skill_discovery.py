"""Ownership checks and native links for one canonical installed skill tree."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from yoke_cli.project_install.files import (
    ProjectInstallError,
    assert_resolved_targets_within,
    remove_empty_parents,
)
from yoke_contracts.project_contract.install_bundle import SKILL_DISCOVERY_LINKS


def validate_links(value: Any) -> dict[str, str]:
    if value != SKILL_DISCOVERY_LINKS:
        raise ProjectInstallError(
            "skill_discovery_contract_unsupported: bundle must name the canonical "
            "Claude discovery link; upgrade the CLI and serving release together"
        )
    return dict(SKILL_DISCOVERY_LINKS)


def preflight(root: Path) -> None:
    """Validate the one native discovery link before any project mutation."""
    try:
        with tempfile.TemporaryDirectory(prefix="yoke-skill-link-") as scratch:
            (Path(scratch) / "entry").symlink_to("source", target_is_directory=True)
    except OSError as exc:
        raise _link_refusal() from exc
    for rel, destination in SKILL_DISCOVERY_LINKS.items():
        assert_resolved_targets_within(root, [rel], context="skill discovery")
        target = root / rel
        if target.is_symlink() and os.readlink(target) == destination:
            continue
        if target.exists() or target.is_symlink():
            _refuse(rel, "an unexpected discovery entry")


def _refuse(rel: str, detail: str) -> None:
    raise ProjectInstallError(
        f"skill_discovery_entry_conflict: {rel} contains {detail}. "
        "Preserve its contents outside the discovery path, then rerun refresh."
    )


def apply(root: Path) -> list[str]:
    """Create the native entry after preflight validates its destination."""
    changed = []
    for rel, destination in SKILL_DISCOVERY_LINKS.items():
        target = root / rel
        if target.is_symlink():
            continue  # preflight already established its exact target
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.symlink_to(destination, target_is_directory=True)
        except OSError as exc:
            raise _link_refusal() from exc
        changed.append(rel)
    return changed


def _link_refusal() -> ProjectInstallError:
    return ProjectInstallError(
        "skill_discovery_link_unavailable: cannot create Claude's native "
        "discovery link. Enable native symlink support (Windows Developer Mode "
        "or administrator permission), then rerun refresh; duplicate skill "
        "copies are unsupported."
    )


def remove(root: Path, records: Any) -> list[str]:
    """Unlink only the exact discovery entries recorded by this installer."""
    if not records:
        return []
    links = validate_links(records)
    removed = []
    for rel, destination in links.items():
        target = root / rel
        assert_resolved_targets_within(root, [rel], context="discovery unlink")
        if target.is_symlink() and os.readlink(target) == destination:
            target.unlink()
            remove_empty_parents(root, rel)
            removed.append(rel)
        elif target.exists() or target.is_symlink():
            _refuse(rel, "a changed discovery entry")
    return removed
