"""Normalize GitHub repository references before project lookup."""

import pytest
from runtime.api.cli.project_onboarding_test_helpers import ProjectOnboardApi
from yoke_cli.config import existing_project_lookup


def test_normalize_github_repo_handles_common_clone_urls() -> None:
    assert (
        existing_project_lookup.normalize_github_repo(
            "https://github.com/Example-Org/ExternalWebapp.git"
        )
        == "example-org/externalwebapp"
    )
    assert (
        existing_project_lookup.normalize_github_repo(
            "git@github.com:Example-Org/ExternalWebapp.git"
        )
        == "example-org/externalwebapp"
    )
    assert existing_project_lookup.normalize_github_repo(
        "Example-Org/ExternalWebapp"
    ) == ("example-org/externalwebapp")
    assert (
        existing_project_lookup.normalize_github_repo(
            "https://ghe.example/Example-Org/ExternalWebapp.git",
            web_url="https://ghe.example",
        )
        == "example-org/externalwebapp"
    )
    assert (
        existing_project_lookup.normalize_github_repo(
            "git@ghe.example:Example-Org/ExternalWebapp.git",
            web_url="https://ghe.example",
        )
        == "example-org/externalwebapp"
    )


def test_normalize_github_repo_rejects_unrelated_or_malformed_paths() -> None:
    assert (
        existing_project_lookup.normalize_github_repo(
            "https://example.test/docs/owner/repo"
        )
        == ""
    )
    assert (
        existing_project_lookup.normalize_github_repo(
            "https://ghe.example/owner/repo/extra"
        )
        == ""
    )
    assert existing_project_lookup.normalize_github_repo("owner") == ""


@pytest.mark.parametrize(
    "value",
    [
        "https://gitlab.com/owner/repo.git",
        "git@gitlab.com:owner/repo.git",
        "https://ghe.example/owner/repo.git",
    ],
)
def test_normalize_github_repo_rejects_foreign_origin(value: str) -> None:
    assert existing_project_lookup.normalize_github_repo(value) == ""


def test_find_by_github_repo_does_not_dispatch_for_foreign_origin() -> None:
    with ProjectOnboardApi() as api:
        project = existing_project_lookup.find_by_github_repo(
            api_url=api.url,
            token="product-token",
            github_repo="https://gitlab.com/owner/demo.git",
        )

    assert project is None
    assert api.function_calls("projects.resolve_by_github_repo") == []
