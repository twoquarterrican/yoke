"""The deployed probe must prove the runner's endpoint through public CLI calls."""

import pytest

from runtime.api.tools import agent_control_plane_probe as probe


@pytest.mark.parametrize(
    "base_url,connection",
    [
        ("", {"transport": "https", "api_url": "https://candidate.test"}),
        ("https://candidate.test", {"transport": "local"}),
        (
            "https://candidate.test",
            {"transport": "https", "api_url": "https://other.test"},
        ),
        (
            "https://candidate.test",
            {"transport": "https", "api_url": "http://candidate.test"},
        ),
        (
            "https://candidate.test",
            {
                "transport": "https",
                "api_url": "https://candidate.test:8443/api/orgs/team",
            },
        ),
        (
            "https://candidate.test",
            {"transport": "https", "api_url": "https://candidate.test:0/api/orgs/team"},
        ),
        (
            "https://candidate.test",
            {"transport": "https", "api_url": "https://candidate.test:invalid"},
        ),
        (
            "https://candidate.test",
            {"transport": "https", "api_url": "https://user@candidate.test"},
        ),
    ],
)
def test_wrong_target_refuses_before_public_calls(
    monkeypatch, capsys, base_url, connection
):
    monkeypatch.setenv("BASE_URL", base_url)
    monkeypatch.setenv("DEPLOYMENT_MEMBER_REF", "YOK-42")
    monkeypatch.setattr(probe, "active_connection", lambda: connection)
    monkeypatch.setattr(
        probe, "call", lambda *a, **k: pytest.fail("wrong endpoint called")
    )
    assert probe.main() == 1
    assert "agent_route_target_mismatch" in capsys.readouterr().err


@pytest.mark.parametrize(
    "api_url",
    [
        "https://candidate.test",
        "https://candidate.test/api/orgs/team",
        "https://CANDIDATE.test:443/api/orgs/team/",
    ],
)
def test_same_origin_accepts_organization_api_path_without_rewriting(
    monkeypatch, api_url
):
    monkeypatch.setenv("BASE_URL", "https://candidate.test/")
    connection = {"transport": "https", "api_url": api_url}
    monkeypatch.setattr(
        probe,
        "active_connection",
        lambda: connection,
    )
    probe.require_target()
    assert connection["api_url"] == api_url
