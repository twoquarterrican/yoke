"""Offline GitHub CLI status preserves cached metadata and secret privacy."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Mapping
from yoke_cli import main as yoke_operations_cli
from yoke_cli.config import github_git_credential_store
from yoke_cli.config import github_merge_path_binding as merge_path_binding
from yoke_contracts import github_app_installation_permissions


def test_github_status_reads_app_config_offline(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("YOKE_MACHINE_HOME", str(tmp_path / "home"))
    config = tmp_path / "machine" / "config.json"
    refresh_file = tmp_path / "github-app-user.json"
    github_git_credential_store.write_credential_document(
        refresh_file,
        {
            "schema_version": 2,
            "refresh_token": "refresh-token",
            "refresh_expires_at": "2027-12-09T17:00:00+00:00",
        },
    )
    permissions = {
        item.key: item.access
        for item in github_app_installation_permissions.REQUIRED_GITHUB_APP_REPOSITORY_PERMISSIONS
    }
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "github": {
                    "api_url": "https://github.example/api/v3",
                    "web_url": "https://github.example",
                    "app_slug": "yoke-local",
                    "app_id": 123,
                    "client_id": "Iv1.local",
                    "profile_source": "service",
                    "profile_service_api_url": "https://api.upyoke.com",
                    "installations": [
                        {
                            "installation_id": 123,
                            "app_id": 123,
                            "app_slug": "yoke-local",
                            "account_login": "octo-org",
                            "account_type": "Organization",
                            "repository_selection": "selected",
                            "suspended": False,
                            "permissions": permissions,
                        }
                    ],
                    "repositories": [
                        {
                            "repository_id": 456,
                            "full_name": "octo-org/app",
                            "default_branch": "main",
                            "installation_id": 123,
                            "private": True,
                        },
                    ],
                    "authorization": {
                        "kind": "github_app_user_authorization",
                        "refresh_credential_ref": str(refresh_file),
                        "login": "cached-user",
                        "github_user_id": 42,
                        "status": "authorized",
                    },
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    config.chmod(0o600)

    rc = yoke_operations_cli.main(
        [
            "github",
            "status",
            "--config",
            str(config),
            "--offline",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["operation"] == "github.status"
    assert payload["connection_model"] == "github_app"
    assert payload["api_url"] == "https://github.example/api/v3"
    assert payload["identity"]["checked"] is False
    assert payload["identity"]["login"] == "cached-user"
    assert payload["authorization"]["present"] is True
    assert "kind" not in payload["authorization"]
    assert "refresh_credential_ref" not in payload["authorization"]
    assert str(refresh_file) not in captured.out
    assert payload["app"]["client_id"] == "Iv1.local"
    assert payload["access"]["owners"] == ["octo-org"]
    assert payload["access"]["repos"] == ["octo-org/app"]
    assert payload["access"]["repositories"] == [
        {
            "repository_id": 456,
            "full_name": "octo-org/app",
            "default_branch": "main",
            "installation_id": 123,
            "private": True,
        }
    ]
    assert payload["permissions"]["ok"] is True
    assert payload["permissions"]["mode"] == "github_app_installation"
    # An offline read proves neither binding, so it never claims readiness.
    assert payload["ready"] is False
    assert {
        name: payload["bindings"][name]["verdict"]
        for name in merge_path_binding.READINESS_BINDINGS
    } == {"user_authorization": "unproven", "app_installation": "unproven"}
    assert payload["access"]["snapshot_source"] == "cached"
    assert payload["access"]["repo_listing_ok"] is None

    written_text = config.read_text(encoding="utf-8")
    _assert_token_absent("refresh-token", captured.out, captured.err, written_text)
    _assert_no_project_runtime_auth(json.loads(written_text))


def _assert_token_absent(token: str, *texts: str) -> None:
    for text in texts:
        assert token not in text


def _assert_no_project_runtime_auth(payload: Mapping[str, Any]) -> None:
    for key in (
        "connections",
        "auth",
        "project_capabilities",
        "capability_secrets",
        "capabilities",
    ):
        assert key not in payload
