"""Branch resolution and merged-branch deployment gate tests."""

from __future__ import annotations

import subprocess
from unittest import mock

from yoke_core.domain import deploy_pipeline_gates


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@test", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class TestFrozenSourceVerification:
    def _repo(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        _git(repo, "commit", "--allow-empty", "-m", "root")
        root_sha = _git(repo, "rev-parse", "HEAD")
        _git(repo, "checkout", "-b", "member")
        _git(repo, "commit", "--allow-empty", "-m", "member work")
        return repo, root_sha

    def test_stale_main_does_not_block_contained_member(self, tmp_path):
        repo, root_sha = self._repo(tmp_path)
        _git(repo, "checkout", "-b", "release-source", "main")
        _git(repo, "merge", "--no-ff", "-m", "land member", "member")
        source_sha = _git(repo, "rev-parse", "HEAD")
        assert _git(repo, "rev-parse", "main") == root_sha
        assert deploy_pipeline_gates._verify_branch_merged(
            "member",
            f"ITEM-{42}",
            str(repo),
            source_sha,
        ) == (True, "")

    def test_newer_main_does_not_admit_member_missing_from_source(self, tmp_path):
        repo, source_sha = self._repo(tmp_path)
        _git(repo, "checkout", "main")
        _git(repo, "merge", "--no-ff", "-m", "land member", "member")
        ok, msg = deploy_pipeline_gates._verify_branch_merged(
            "member",
            f"ITEM-{42}",
            str(repo),
            source_sha,
        )
        assert not ok
        assert "release_member_not_in_source" in msg
        assert source_sha in msg
        assert "compose a new run" in msg

    def test_squash_evidence_is_checked_in_frozen_source(self, tmp_path):
        repo, root_sha = self._repo(tmp_path)
        _git(repo, "checkout", "-b", "release-source", "main")
        _git(repo, "commit", "--allow-empty", "-m", f"Squash ITEM-{42}")
        source_sha = _git(repo, "rev-parse", "HEAD")
        ok, msg = deploy_pipeline_gates._verify_branch_merged(
            "member",
            f"ITEM-{42}",
            str(repo),
            source_sha,
        )
        assert ok and "Squash-merge detected" in msg
        ok, _ = deploy_pipeline_gates._verify_branch_merged(
            "member",
            f"ITEM-{42}",
            str(repo),
            root_sha,
        )
        assert not ok
        _git(repo, "branch", "-D", "member")
        assert deploy_pipeline_gates._verify_branch_merged(
            "member",
            f"ITEM-{42}",
            str(repo),
            source_sha,
        ) == (True, "")

    def test_unreadable_source_refuses_with_recovery(self, tmp_path):
        repo, _ = self._repo(tmp_path)
        for source in ("", "main", "a" * 40):
            ok, msg = deploy_pipeline_gates._verify_branch_merged(
                "member",
                f"ITEM-{42}",
                str(repo),
                source,
            )
            assert not ok
            assert "release_source_unavailable" in msg
            assert "repair its release lineage" in msg

    def test_missing_branch_warning_names_frozen_source(self, tmp_path):
        repo, source_sha = self._repo(tmp_path)
        for branch in ("", "null"):
            ok, msg = deploy_pipeline_gates._verify_branch_merged(
                branch,
                f"ITEM-{42}",
                str(repo),
                source_sha,
            )
            assert ok
            assert "no branch set" in msg
            assert source_sha in msg


class TestResolveFlowGateBranch:
    """Gate branch = target environment branch, else project base branch."""

    def test_declared_env_branch_wins(self):
        with mock.patch(
            "yoke_core.domain.deploy_environment_settings.declared_env_branch",
            return_value="stage",
        ) as declared:
            assert (
                deploy_pipeline_gates.resolve_flow_gate_branch(
                    "yoke",
                    "persistent",
                    "stage",
                )
                == "stage"
            )
        declared.assert_called_once_with("yoke", "stage")

    def test_no_target_environment_falls_back_to_base_branch(self):
        with mock.patch(
            "yoke_core.domain.project_settings.get_project_str",
            return_value="main",
        ) as get_project_str:
            assert (
                deploy_pipeline_gates.resolve_flow_gate_branch("yoke", "", "") == "main"
            )
        get_project_str.assert_called_once_with("", "base_branch")

    def test_env_without_declared_branch_falls_back(self):
        with (
            mock.patch(
                "yoke_core.domain.deploy_environment_settings.declared_env_branch",
                return_value="",
            ),
            mock.patch(
                "yoke_core.domain.project_settings.get_project_str",
                return_value="main",
            ),
        ):
            assert (
                deploy_pipeline_gates.resolve_flow_gate_branch(
                    "externalwebapp",
                    "persistent",
                    "prod",
                )
                == "main"
            )

    def test_repo_root_is_passed_to_base_branch_policy_reader(self, tmp_path):
        repo = tmp_path / "checkout"
        with mock.patch(
            "yoke_core.domain.project_settings.get_project_str",
            return_value="trunk",
        ) as get_project_str:
            assert (
                deploy_pipeline_gates.resolve_flow_gate_branch(
                    "externalwebapp",
                    "",
                    "",
                    str(repo),
                )
                == "trunk"
            )
        get_project_str.assert_called_once_with(str(repo), "base_branch")

    def test_ephemeral_tier_has_no_gate_branch(self):
        """Ephemeral preview flows deploy unmerged branches."""
        assert (
            deploy_pipeline_gates.resolve_flow_gate_branch(
                "yoke",
                "ephemeral",
                "",
            )
            == ""
        )


class TestEphemeralTierBranchResolution:
    def test_empty_gate_branch_skips_merged_verification(self, capsys):
        ok, first_item, branch = deploy_pipeline_gates._resolve_and_verify_branch(
            ["42"],
            "/repo",
            target_branch="",
            source_sha="a" * 40,
            first_branch="my-branch",
            sd=None,
        )
        assert (ok, first_item, branch) == (True, "42", "my-branch")
        assert "Ephemeral tier" in capsys.readouterr().out
