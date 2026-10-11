"""Positive install ownership and interrupted-apply recovery."""

import json
import subprocess
import pytest
from yoke_cli.project_install import install_recovery as recovery
from yoke_cli.project_install import instruction_discovery, skill_discovery
from yoke_cli.project_install.bundle_apply import apply_bundle
from yoke_cli.project_install.files import ProjectInstallError, sha256_text
from yoke_core.domain.project_install_test_helpers import make_bundle


def _file(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )


def _commit(root, message):
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=Installer",
        "-c",
        "user.email=installer@example.test",
        "commit",
        "-m",
        message,
    )


def test_bundle_proves_unrecorded_legacy_copy_and_refuses_edit(tmp_path):
    rel = ".codex/skills/yoke/onboard/SKILL.md"
    path = _file(tmp_path, rel, "released skill\n")
    bundle = {
        "files": [
            {
                "path": ".agents/skills/yoke/onboard/SKILL.md",
                "content": "released skill\n",
            }
        ]
    }
    assert skill_discovery.preflight(tmp_path, {}, bundle) == {
        rel: sha256_text("released skill\n")
    }
    path.write_text("local edit\n")
    with pytest.raises(
        ProjectInstallError, match="skill_discovery_ownership_ambiguous"
    ):
        skill_discovery.preflight(tmp_path, {}, bundle)
    assert path.read_text() == "local edit\n"


@pytest.mark.parametrize(
    "subject",
    [
        "Install Yoke operating layer 1.0.0",
        "Refresh the installed Yoke operating layer to 1.0.0",
    ],
)
def test_installer_history_proves_old_copy_and_refuses_user_commit(tmp_path, subject):
    rel = ".claude/skills/yoke/onboard/SKILL.md"
    _git(tmp_path, "init")
    path = _file(tmp_path, rel, "old release\n")
    _commit(tmp_path, subject)
    assert skill_discovery.preflight(tmp_path, {}) == {
        rel: sha256_text("old release\n")
    }
    path.write_text("uncommitted edit\n")
    with pytest.raises(
        ProjectInstallError, match="skill_discovery_ownership_ambiguous"
    ):
        skill_discovery.preflight(tmp_path, {})
    _commit(tmp_path, "Customize skill")
    with pytest.raises(
        ProjectInstallError, match="skill_discovery_ownership_ambiguous"
    ):
        skill_discovery.preflight(tmp_path, {})


def test_record_ahead_of_installer_content_is_repaired(tmp_path, monkeypatch):
    monkeypatch.setattr(instruction_discovery.shutil, "which", lambda _: None)
    bundle = make_bundle()
    _git(tmp_path, "init")
    rel = bundle["files"][0]["path"]
    _file(tmp_path, rel, "older installer content\n")
    _commit(tmp_path, "Install Yoke operating layer 1.0.0")
    prior = {
        "manifest_schema": 1,
        "files": {rel: sha256_text("newer release content\n")},
    }
    report = apply_bundle(tmp_path, bundle, prior_manifest=prior)
    assert rel in report["install_drift"]["changed"]
    assert (tmp_path / rel).read_text() == bundle["files"][0]["content"]


def test_missing_and_half_applied_files_converge_then_refresh_is_clean(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(instruction_discovery.shutil, "which", lambda _: None)
    bundle = make_bundle()
    apply_bundle(tmp_path, bundle)
    rel = bundle["files"][0]["path"]
    (tmp_path / rel).unlink()
    assert apply_bundle(tmp_path, bundle)["install_drift"]["missing"] == [rel]
    newer = dict(
        bundle,
        files=[
            dict(e, content=e["content"] + "\nnew release\n") for e in bundle["files"]
        ],
    )
    original = recovery.atomic_text
    calls = 0

    def interrupted(path, text):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("simulated power loss")
        original(path, text)

    monkeypatch.setattr(recovery, "atomic_text", interrupted)
    with pytest.raises(OSError, match="simulated power loss"):
        apply_bundle(tmp_path, newer)
    assert recovery.pending(tmp_path)
    newest = dict(
        newer,
        files=[
            dict(e, content=e["content"] + "another release\n") for e in newer["files"]
        ],
    )
    monkeypatch.setattr(recovery, "atomic_text", original)
    assert apply_bundle(tmp_path, newest)["install_drift"]["interrupted"]
    assert not recovery.pending(tmp_path)
    assert apply_bundle(tmp_path, newest)["files_written"] == []
    manifest = json.loads((tmp_path / ".yoke/install-manifest.json").read_text())
    assert all(
        sha256_text((tmp_path / p).read_text()) == sha
        for p, sha in manifest["files"].items()
    )


def test_local_canonical_edits_refuse_before_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(instruction_discovery.shutil, "which", lambda _: None)
    bundle = make_bundle()
    apply_bundle(tmp_path, bundle)
    path = _file(tmp_path, bundle["files"][0]["path"], "my local edit\n")
    with pytest.raises(ProjectInstallError, match="install_drift_local_edits"):
        apply_bundle(tmp_path, bundle)
    assert path.read_text() == "my local edit\n"
    assert not recovery.pending(tmp_path)


@pytest.mark.parametrize("failure", ["replace", "mkstemp"])
def test_failed_atomic_write_keeps_prior_manifest(tmp_path, monkeypatch, failure):
    path = _file(tmp_path, ".yoke/install-manifest.json", '{"old": true}\n')

    def refuse(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(
        recovery.os if failure == "replace" else recovery.tempfile, failure, refuse
    )
    with pytest.raises(ProjectInstallError, match="install_write_failed"):
        recovery.atomic_text(path, '{"new": true}\n')
    assert path.read_text() == '{"old": true}\n'
    assert list(path.parent.iterdir()) == [path]


def test_tagged_release_proves_manually_refreshed_copy(tmp_path, monkeypatch):
    from yoke_cli.project_install import released_bundle_files

    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init")
    _file(source, ".agents/skills/yoke/onboard/SKILL.md", "archived release\n")
    _commit(source, "Publish authored skill")
    _git(
        source,
        "-c",
        "user.name=Publisher",
        "-c",
        "user.email=publisher@example.test",
        "tag",
        "-a",
        "v1.0.0",
        "-m",
        "Release",
    )
    target = tmp_path / "consumer"
    target.mkdir()
    rel = ".claude/skills/yoke/onboard/SKILL.md"
    path = _file(target, rel, "archived release\n")
    monkeypatch.setattr(released_bundle_files, "source_checkout_root", lambda _: source)
    assert skill_discovery.preflight(target, {}) == {
        rel: sha256_text("archived release\n")
    }
    path.write_text("local changes\n")
    with pytest.raises(
        ProjectInstallError, match="skill_discovery_ownership_ambiguous"
    ):
        skill_discovery.preflight(target, {})


def test_committed_instruction_drift_retires_block_preserving_user_text(tmp_path):
    from yoke_contracts.project_contract.managed_block import render_block

    _git(tmp_path, "init")
    path = _file(
        tmp_path, "CODEX.md", "User instructions\n" + render_block("old release")
    )
    _commit(tmp_path, "Install Yoke operating layer 1.0.0")
    prior = {
        "managed_markdown": {
            "CODEX.md": {"block_sha": sha256_text(render_block("later release"))}
        }
    }
    planned = instruction_discovery.retirement_plan(tmp_path, prior)
    assert planned["CODEX.md"] == "User instructions\n"
    path.write_text("User instructions\n" + render_block("local edit"))
    with pytest.raises(ProjectInstallError, match="instruction_ownership_ambiguous"):
        instruction_discovery.retirement_plan(tmp_path, prior)


def test_dirty_interrupted_checkout_accepts_planned_settings_and_refuses_edits(
    tmp_path, monkeypatch
):
    from yoke_cli.project_install.preflight import preflight_apply

    monkeypatch.setattr(instruction_discovery.shutil, "which", lambda _: None)
    _git(tmp_path, "init")
    _file(tmp_path, "README.md", "project\n")
    _commit(tmp_path, "Create project")
    bundle = make_bundle()
    bundle["hooks"]["cursor_hooks"] = {}
    preflight = preflight_apply(tmp_path, bundle, {}, {})
    recovery.begin(tmp_path, preflight["install_recovery"])
    _file(
        tmp_path,
        ".claude/settings.json",
        json.dumps(
            preflight["hook_plans"][".claude/settings.json"]["payload"], indent=2
        )
        + "\n",
    )
    # Git reports untracked directories by default; production's porcelain reader expands them.
    assert recovery.recoverable_checkout(tmp_path)
    _file(tmp_path, "README.md", "new user edit\n")
    assert not recovery.recoverable_checkout(tmp_path)


def test_packaged_release_hashes_prove_old_bytes_without_source(tmp_path, monkeypatch):
    from yoke_cli.project_install import released_bundle_files as released

    content = "immutable released skill\n"
    monkeypatch.setattr(released, "source_checkout_root", lambda _: None)
    monkeypatch.setattr(
        released, "_catalogue", lambda: {"skills/old/SKILL.md": [sha256_text(content)]}
    )
    proof = released.ReleasedBundleFiles()
    assert proof.proves(".codex/skills/yoke/old/SKILL.md", content)
    assert not proof.proves(".codex/skills/yoke/old/SKILL.md", "user edit\n")


def test_commit_recovers_deleted_installer_output_and_discovery_link(tmp_path):
    from yoke_cli.project_install import checkout_gate
    from yoke_cli.project_install.files import write_manifest

    _git(tmp_path, "init")
    old = _file(tmp_path, ".yoke/docs/retired.md", "old installed doc\n")
    legacy = _file(tmp_path, ".claude/skills/yoke/SKILL.md", "old installed skill\n")
    _file(tmp_path, "AGENTS.md", "old instructions\n")
    _commit(tmp_path, "Install Yoke operating layer 1.0.0")
    old.unlink()
    legacy.unlink()
    legacy.parent.rmdir()
    _file(tmp_path, ".agents/skills/yoke/SKILL.md", "new skill\n")
    legacy.parent.symlink_to("../../.agents/skills/yoke", target_is_directory=True)
    _file(tmp_path, "AGENTS.md", "new instructions\n")
    write_manifest(
        tmp_path,
        {
            "files": {".agents/skills/yoke/SKILL.md": sha256_text("new skill\n")},
            "manifest_schema": 1,
            "managed_markdown": {
                "AGENTS.md": {"block_sha": sha256_text("new instructions\n")}
            },
        },
    )
    report = {"yoke_version": "1.0.1", "skill_discovery_paths": [".claude/skills/yoke"]}
    receipt = checkout_gate.commit_touched_paths(tmp_path, report, operation="refresh")
    assert receipt["status"] == "created"
    assert ".yoke/docs/retired.md" in receipt["paths"]
    assert not checkout_gate.porcelain(tmp_path)


def test_commit_touched_paths_on_non_git_checkout(tmp_path):
    from yoke_cli.project_install import checkout_gate

    assert (
        checkout_gate.commit_touched_paths(tmp_path, {})["reason"]
        == "not a git checkout"
    )


def test_apply_retains_recovery_until_commit_and_retry_converges(tmp_path, monkeypatch):
    monkeypatch.setattr(instruction_discovery.shutil, "which", lambda _: None)
    from yoke_cli.project_install import checkout_gate

    _git(tmp_path, "init")
    _file(tmp_path, "README.md", "project\n")
    _commit(tmp_path, "Create project")
    report = apply_bundle(tmp_path, make_bundle(), retain_pending=True)
    assert recovery.pending(tmp_path)
    assert recovery.recoverable_checkout(tmp_path)
    original = checkout_gate.run_git

    def fail_commit(root, *args):
        if "commit" in args:
            return subprocess.CompletedProcess(args, 1, "", "simulated commit failure")
        return original(root, *args)

    monkeypatch.setattr(checkout_gate, "run_git", fail_commit)
    with pytest.raises(ProjectInstallError, match="could not commit"):
        checkout_gate.commit_touched_paths(tmp_path, report)
    assert recovery.pending(tmp_path)
    assert recovery.recoverable_checkout(tmp_path)
    monkeypatch.setattr(checkout_gate, "run_git", original)
    retried = apply_bundle(tmp_path, make_bundle(), retain_pending=True)
    checkout_gate.commit_touched_paths(tmp_path, retried)
    recovery.finish(tmp_path, recovery.pending(tmp_path))
    assert not recovery.pending(tmp_path)
    assert not checkout_gate.porcelain(tmp_path)
