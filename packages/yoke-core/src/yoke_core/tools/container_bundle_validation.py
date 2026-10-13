"""Stage release sources and exercise project-bundle rendering in the image."""

from __future__ import annotations

import argparse
from pathlib import Path

from yoke_core.domain.install_bundle_sources import (
    HARNESS_MANIFEST_SOURCES,
    INSTALL_BUNDLE_SOURCE_FILES,
    source_file_bytes,
)


def stage_source_files(source_root: Path, destination: Path) -> None:
    """Preserve canonical relative paths without duplicating a Docker file list."""
    for relative in INSTALL_BUNDLE_SOURCE_FILES:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source_file_bytes(source_root / relative))


def verify_project_bundle(root: Path) -> dict:
    """Render against real image files, replacing only project database state."""
    from unittest.mock import Mock, patch

    from yoke_core.domain import install_bundle, install_bundle_project
    from yoke_core.domain import project_policy_capabilities

    # Image construction has no tenant database. Keep every filesystem reader
    # and renderer real while supplying the project-owned database boundaries.
    with (
        patch.object(install_bundle, "server_tree_root", return_value=root),
        patch.object(
            install_bundle_project,
            "_project_row",
            return_value=("image-check", "Image check", "main"),
        ),
        patch.object(install_bundle_project, "_strategy_files", return_value=[]),
        patch.object(
            project_policy_capabilities,
            "ensure_default_policy_capabilities",
            return_value={},
        ),
    ):
        bundle = install_bundle_project.build_project_bundle(1, Mock())
    files = {entry["path"]: entry["content"] for entry in bundle["files"]}
    for relative in HARNESS_MANIFEST_SOURCES:
        installed = relative.replace("runtime/harness/", ".yoke/harness/", 1)
        assert files[installed].encode() == (root / relative).read_bytes()
    assert files[".yoke/docs/index.md"]
    assert files[".agents/skills/yoke/help/SKILL.md"]
    assert bundle["managed_markdown"]["blocks"]["doctrine"]
    return bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage-source-files")
    stage.add_argument("source_root", type=Path)
    stage.add_argument("destination", type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    if args.command == "stage-source-files":
        stage_source_files(args.source_root, args.destination)
    else:
        bundle = verify_project_bundle(args.root)
        print(f"container project bundle passed: {len(bundle['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
