"""Manifest transfer preserves unrelated files and prunes dropped canonical output."""

import hashlib
import json
from pathlib import Path

from yoke_cli.main import main as cli_main
from runtime.api.cli.project_refresh_test_support import (
    REPO_ROOT,
    _git_init,
    _seed_manifest,
)


def test_manifest_transfer_prunes_dropped_file_in_linked_checkout(
    tmp_path: Path,
    capsys,
) -> None:
    main_checkout = tmp_path / "project-main"
    linked_checkout = tmp_path / "project-worktree"
    _git_init(main_checkout)
    _git_init(linked_checkout)
    _seed_manifest(main_checkout, 43)
    base_args = [
        "project",
        "refresh",
        str(main_checkout),
        "--source-checkout",
        str(REPO_ROOT),
        "--project-id",
        "43",
        "--force",
        "--no-commit",
        "--apply",
        "--json",
    ]
    assert cli_main(base_args) == 0
    capsys.readouterr()

    obsolete_content = "old generated content\n"
    obsolete_hash = hashlib.sha256(obsolete_content.encode("utf-8")).hexdigest()
    manifest_path = main_checkout / ".yoke/install-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    obsolete_rel = ".agents/skills/yoke/obsolete/SKILL.md"
    manifest["files"][obsolete_rel] = obsolete_hash
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    obsolete_path = linked_checkout / obsolete_rel
    obsolete_path.parent.mkdir(parents=True)
    obsolete_path.write_text(obsolete_content, encoding="utf-8")
    assert not (linked_checkout / ".yoke/install-manifest.json").exists()

    rc = cli_main(
        [
            "project",
            "refresh",
            str(linked_checkout),
            "--source-checkout",
            str(REPO_ROOT),
            "--manifest-from",
            str(manifest_path),
            "--force",
            "--no-commit",
            "--apply",
            "--json",
        ]
    )

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["manifest_source"] == str(manifest_path.resolve())
    assert report["files_pruned"] == [obsolete_rel]
    assert not obsolete_path.exists()
    assert (linked_checkout / ".yoke/install-manifest.json").is_file()


def test_full_manifest_preserves_unrendered_workflow_and_contract(
    tmp_path: Path,
    capsys,
) -> None:
    target = tmp_path / "external-project"
    _git_init(target)
    workflow_rel = ".github/workflows/deploy.yml"
    workflow_content = "name: deploy\non: workflow_dispatch\n"
    removed_source_rel = ".agents/skills/yoke/removed/SKILL.md"
    removed_source_content = "# removed source skill\n"
    contract_rel = ".yoke/lint-config"
    contract_content = "lint_main_commit=deny\n"
    for rel, content in (
        (workflow_rel, workflow_content),
        (removed_source_rel, removed_source_content),
        (contract_rel, contract_content),
    ):
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest_path = target / ".yoke/install-manifest.json"
    initial_manifest = {
        "manifest_schema": 1,
        "yoke_version": "packaged-baseline",
        "project_id": 46,
        "project_slug": "workflow-project",
        "mode": "copy",
        "files": {
            workflow_rel: hashlib.sha256(workflow_content.encode("utf-8")).hexdigest(),
            removed_source_rel: hashlib.sha256(
                removed_source_content.encode("utf-8")
            ).hexdigest(),
        },
        "contract_files": {
            contract_rel: hashlib.sha256(contract_content.encode("utf-8")).hexdigest(),
        },
        "strategy_files": {},
        "created_settings_files": [],
        "hook_entries": {},
    }
    manifest_path.write_text(
        json.dumps(initial_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args = [
        "project",
        "refresh",
        str(target),
        "--source-checkout",
        str(REPO_ROOT),
        "--json",
    ]

    assert cli_main(args) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["project_slug"] == "workflow-project"
    assert preview["files_preserved_unrendered"] == [workflow_rel]
    assert preview["files_would_prune"] == [removed_source_rel]
    assert (target / workflow_rel).read_text(encoding="utf-8") == workflow_content
    assert (target / contract_rel).read_text(encoding="utf-8") == contract_content

    assert cli_main([*args[:-1], "--force", "--no-commit", "--apply", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["files_preserved_unrendered"] == [workflow_rel]
    assert report["files_pruned"] == [removed_source_rel]
    assert (target / workflow_rel).read_text(encoding="utf-8") == workflow_content
    assert (target / contract_rel).read_text(encoding="utf-8") == contract_content
    refreshed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert refreshed["project_slug"] == "workflow-project"
    assert refreshed["files"][workflow_rel] == (initial_manifest["files"][workflow_rel])
    assert (
        refreshed["contract_files"][contract_rel]
        == (initial_manifest["contract_files"][contract_rel])
    )
