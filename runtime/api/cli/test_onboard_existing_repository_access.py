"""Live existing-repository discovery and exact installation settings recovery."""

from types import SimpleNamespace

import pytest

from yoke_cli.config import onboard_wizard_project_github as access
from yoke_cli.config import onboard_wizard_github_state as state
from yoke_contracts import github_origin, github_app_installation_permissions


class Flow(access.ProjectGithubAccessFlow):
    def __init__(self):
        self.result = SimpleNamespace(
            project_github_repo="acme/widget",
            config_path=None,
            destination="local",
            api_url="",
            project_github_repository_id=99,
            project_github_installation_id=98,
        )
        self.bound = False

    def _run_checking(self, **kwargs):
        self.checking = kwargs

    def _goto(self, view):
        self.details = view.builder()

    def _goto_board_art(self):
        self.bound = True


@pytest.fixture
def setup(monkeypatch):
    config = {
        "installations": [
            {
                "installation_id": 7,
                "account_login": "acme",
                "account_type": "Organization",
                "repository_selection": "selected",
                "permissions": dict(
                    github_app_installation_permissions.REQUIRED_GITHUB_APP_REPOSITORY_PERMISSION_LEVELS
                ),
            }
        ],
        "repositories": [],
    }
    monkeypatch.setattr(access.machine_config, "github_config", lambda _: config)
    monkeypatch.setattr(access, "github_connected", lambda _: True)
    monkeypatch.setattr(
        access.steps,
        "verification_body",
        lambda _title, _subtitle, details, *_args, **_kwargs: details,
    )
    monkeypatch.setattr(
        access, "open_url", lambda _: pytest.fail("unexpected browser launch")
    )
    return Flow(), config


def report(repositories, listing_ok=True):
    return {
        "identity": {"checked": True, "ok": True},
        "access": {
            "repo_listing_ok": listing_ok,
            "repositories": repositories,
        },
    }


@pytest.mark.parametrize(
    "choice", [access.PROJECT_GITHUB_REUSE_MACHINE, access.GITHUB_ADOPTION_APP_BINDING]
)
def test_existing_repo_choices_always_check_live_and_bind_exact_repo(
    setup, monkeypatch, choice
):
    flow, config = setup
    repository = {"full_name": "ACME/Widget", "repository_id": 81, "installation_id": 7}
    calls = []
    monkeypatch.setattr(
        access.github_machine,
        "status",
        lambda **kwargs: calls.append(kwargs) or report([repository]),
    )
    flow._on_project_github(choice)
    assert not flow.bound
    assert flow.result.project_github_repository_id is None
    flow.checking["on_success"](flow.checking["work"]())
    assert calls[0]["check"] is True
    assert calls[0]["local_connection_selected"] is True
    assert flow.bound
    assert flow.result.project_github_repository_id == 81
    assert flow.result.project_github_installation_id == 7
    assert config["repositories"] == []


def test_live_missing_repo_ignores_cached_presence_and_teaches_exact_settings(setup):
    flow, config = setup
    config["repositories"] = [{"full_name": "acme/widget", "installation_id": 7}]
    flow._on_project_github(access.PROJECT_GITHUB_REUSE_MACHINE)
    flow.checking["on_success"](report([]))
    assert not flow.bound
    text = " ".join(flow.details)
    assert "Your Yoke app can see selected repos only. Add acme/widget here." in text
    assert "https://github.com/organizations/acme/settings/installations/7" in text
    assert "browser did not open" not in text


@pytest.mark.parametrize(
    "failure", [report([], False), RuntimeError("network_timeout")]
)
def test_failed_live_check_does_not_claim_repository_missing(setup, failure):
    flow, _ = setup
    flow._on_project_github(access.PROJECT_GITHUB_REUSE_MACHINE)
    if isinstance(failure, Exception):
        flow.checking["on_error"](failure)
    else:
        flow.checking["on_success"](failure)
    text = " ".join(flow.details)
    assert "repository_access_unknown" in text
    assert "Check access again" in text
    assert "selected repos only" not in text
    assert not flow.bound


@pytest.mark.parametrize(
    "kind,path",
    [
        ("User", "/settings/installations/7"),
        ("Organization", "/organizations/acme/settings/installations/7"),
    ],
)
@pytest.mark.parametrize(
    "web,api",
    [
        ("https://github.com", "https://api.github.com"),
        ("https://git.example", "https://git.example/api/v3"),
    ],
)
def test_settings_built_from_identity_when_url_missing_or_unsafe(
    setup, kind, path, web, api
):
    flow, config = setup
    config.update(web_url=web, api_url=api)
    config["installations"][0].update(
        account_type=kind, html_url="https://attacker.example"
    )
    assert state.repository_access_url(flow.result, owner="ACME") == web + path


@pytest.mark.parametrize("identity", [None, True, 0, "7"])
def test_missing_installation_identity_names_recovery_never_returns_origin(
    setup, identity
):
    flow, config = setup
    config["installations"][0]["installation_id"] = identity
    with pytest.raises(
        github_origin.GitHubApiOriginError,
        match="github_installation_settings_unavailable.*Reconnect",
    ):
        state.repository_access_url(flow.result, owner="acme")
    flow._after_project_github_access_refresh(report([]))
    assert "github_installation_settings_unavailable" in " ".join(flow.details)


def test_wrong_owner_does_not_link_another_installation(setup):
    flow, _ = setup
    with pytest.raises(
        github_origin.GitHubApiOriginError,
        match="github_installation_settings_unavailable",
    ):
        state.repository_access_url(flow.result, owner="other")
