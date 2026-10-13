"""Execute public project recipes using the default machine configuration."""

from __future__ import annotations

import json

import pytest

from runtime.api.cli.project_onboarding_test_helpers import (
    ProjectOnboardApi,
    write_https_config,
    seed_remote,
    run_git,
    git_output,
)
from runtime.api.cli.project_clone_test_support import allow_local_clone
from yoke_cli.main import main

pytestmark = pytest.mark.usefixtures("stub_onboard_session_relay")


@pytest.mark.parametrize("operation", ["create", "import", "onboard"])
def test_project_recipe_without_config_or_github(
    tmp_path, monkeypatch, capsys, operation
):
    monkeypatch.setenv("YOKE_MACHINE_HOME", str(tmp_path / "machine-home"))
    monkeypatch.delenv("YOKE_MACHINE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("YOKE_ENV", raising=False)
    checkout = tmp_path / "checkout"
    if operation == "import":
        remote = seed_remote(tmp_path)
        allow_local_clone(monkeypatch)
        args = ["project", "import", str(remote), str(checkout)]
    elif operation == "onboard":
        checkout.mkdir()
        run_git(checkout, "init", "--initial-branch", "main")
        run_git(
            checkout,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "initial",
        )
        args = ["onboard", "project", str(checkout)]
    else:
        args = ["project", "create", str(checkout)]
    branch = "trunk" if operation == "import" else "main"
    with ProjectOnboardApi(
        project={
            "id": 41,
            "slug": "demo",
            "name": "Demo",
            "github_repo": "",
            "default_branch": branch,
            "public_item_prefix": "DMO",
        }
    ) as api:
        config = write_https_config(tmp_path, "product-token", api.url)
        assert (
            main(
                args
                + [
                    "--slug",
                    "demo",
                    "--name",
                    "Demo",
                    "--default-branch",
                    branch,
                    "--public-item-prefix",
                    "DMO",
                    "--github-adoption",
                    "disabled",
                    "--yes",
                    "--json",
                ]
            )
            == 0
        )
        report = json.loads(capsys.readouterr().out)
    assert report["applied"] is True
    assert report["checkout"]["registered"] is True
    assert (checkout / ".yoke/install-manifest.json").is_file()
    assert "github" not in json.loads(config.read_text())
    if operation != "import":
        assert git_output(checkout, "remote") == ""
    assert git_output(checkout, "status", "--porcelain") == ""
    if operation != "onboard":
        assert (
            api.function_call("projects.create")["payload"]["github_sync_mode"]
            == "disabled"
        )


def test_missing_default_config_teaches_setup(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("YOKE_MACHINE_HOME", str(tmp_path / "missing-home"))
    monkeypatch.delenv("YOKE_MACHINE_CONFIG_FILE", raising=False)
    monkeypatch.delenv("YOKE_ENV", raising=False)
    assert (
        main(
            [
                "project",
                "create",
                str(tmp_path / "checkout"),
                "--slug",
                "demo",
                "--name",
                "Demo",
                "--default-branch",
                "main",
                "--public-item-prefix",
                "DMO",
                "--github-adoption",
                "disabled",
                "--yes",
            ]
        )
        != 0
    )
    output = capsys.readouterr()
    assert "config" in output.err.lower()
    assert "Traceback" not in output.err
    assert not (tmp_path / "checkout").exists()
