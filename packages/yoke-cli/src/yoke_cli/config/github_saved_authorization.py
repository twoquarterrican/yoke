"""Reuse verified GitHub user authorization before asking for another code."""

from __future__ import annotations

from typing import Any

from yoke_cli.config import github_machine_status, github_app_public_profile


def reuse(
    *,
    existing: dict[str, Any],
    metadata: dict[str, Any],
    replace_profile: bool,
    **status_kwargs: Any,
) -> dict[str, Any] | None:
    if not existing or replace_profile:
        return None
    local = metadata.get("profile_source") in {
        github_app_public_profile.PROFILE_SOURCE_LOCAL_EXPLICIT,
        github_app_public_profile.PROFILE_SOURCE_LOCAL_PRODUCT,
    }
    report = github_machine_status.status(
        check=True, local_connection_selected=local, **status_kwargs
    )
    binding = report.get("bindings", {}).get("user_authorization", {})
    if binding.get("verdict") == "broken":
        return None
    if binding.get("verdict") not in {"ok", "busy"}:
        raise status_kwargs.get("error_type", RuntimeError)(
            "github_authorization_status_unknown: run yoke github status and repair its reported binding before reconnecting"
        )
    report.update({"operation": "github.connect", "authorization_reused": True})
    return report
