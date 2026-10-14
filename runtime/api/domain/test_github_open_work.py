"""Open GitHub work is read where the project's repository binding is.

Onboarding lists a project's open issues and pull requests before proposing
work, from a session that may hold no GitHub credential and no host CLI.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from runtime.api.domain.handlers.deployment_handler_test_support import (
    deployment_request as _request,
)
from yoke_contracts.api.function_call import TargetRef
from yoke_contracts.function_serving_floors import FUNCTION_MINIMUM_SERVING_VERSIONS
from yoke_core.domain import gh_rest_transport, project_github_auth
from yoke_core.domain.function_authz_scope import classify
from yoke_core.domain.function_authz_types import PROJECT
from yoke_core.domain.gh_rest_transport import RestAuthError, RestResponse
from yoke_core.domain.handlers import github_open_work as handler

TOKEN = "ghs_secret_token_value"


class _Resolved:
    repo = "acme/widgets"
    token = TOKEN


def _issue(number: int, *, pull: bool = False) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "number": number,
        "title": f"issue {number}",
        "labels": [{"name": "bug"}, {"name": ""}],
        "updated_at": f"2026-10-{number % 28 + 1:02d}T00:00:00Z",
        "html_url": f"https://github.com/acme/widgets/issues/{number}",
    }
    if pull:
        entry["pull_request"] = {"url": "x"}
    return entry


def _pull(number: int) -> Dict[str, Any]:
    return {
        "number": number,
        "title": f"pull {number}",
        "head": {"ref": f"branch-{number}"},
        "draft": number % 2 == 0,
        "updated_at": "2026-10-01T00:00:00Z",
        "html_url": f"https://github.com/acme/widgets/pull/{number}",
    }


class _Transport:
    """Serve pages per path; record every request."""

    def __init__(self, pages: Dict[str, List[List[Dict[str, Any]]]], error=None):
        self.pages = pages
        self.error = error
        self.requests: List[Any] = []

    def __call__(self, req, *, token):
        assert token == TOKEN
        self.requests.append(req)
        if self.error is not None:
            raise self.error
        series = self.pages[req.path.rsplit("/", 1)[1]]
        index = int(req.query["page"]) - 1
        body = series[index] if index < len(series) else []
        return RestResponse(status=200, headers={}, body=body)


def _bind(monkeypatch, transport, resolve=None) -> None:
    def default_resolve(project, *, required_permissions):
        assert project == "widgets"
        assert required_permissions == {"issues": "read", "pull_requests": "read"}
        return _Resolved()

    monkeypatch.setattr(
        project_github_auth, "resolve_project_github_auth", resolve or default_resolve
    )
    monkeypatch.setattr(gh_rest_transport, "request_with_retry", transport)


def _call(payload=None):
    return handler.handle_open_work_list(
        _request(
            function=handler.FUNCTION_ID,
            target=TargetRef(kind="global"),
            payload={"project": "widgets", **(payload or {})},
        )
    )


def test_issues_drop_pull_requests_and_pulls_come_from_the_pulls_endpoint(
    monkeypatch,
) -> None:
    transport = _Transport(
        {
            "issues": [[_issue(1), _issue(2, pull=True), _issue(3)]],
            "pulls": [[_pull(2), _pull(5)]],
        }
    )
    _bind(monkeypatch, transport)
    outcome = _call()
    assert outcome.primary_success, outcome.error
    result = outcome.result_payload
    assert result["repo"] == "acme/widgets"
    assert [row["number"] for row in result["issues"]] == [1, 3]
    assert result["issues"][0]["labels"] == ["bug"]
    assert result["issues"][0]["url"].endswith("/issues/1")
    assert result["pull_requests"] == [
        {
            "number": 2,
            "title": "pull 2",
            "head_ref": "branch-2",
            "draft": True,
            "updated_at": "2026-10-01T00:00:00Z",
            "url": "https://github.com/acme/widgets/pull/2",
        },
        {
            "number": 5,
            "title": "pull 5",
            "head_ref": "branch-5",
            "draft": False,
            "updated_at": "2026-10-01T00:00:00Z",
            "url": "https://github.com/acme/widgets/pull/5",
        },
    ]
    assert result["truncated"] is False
    for req in transport.requests:
        assert req.method == "GET"
        assert req.query["state"] == "open"
        assert req.query["sort"] == "updated"
        assert req.query["direction"] == "desc"
    assert {req.path for req in transport.requests} == {
        "/repos/acme/widgets/issues",
        "/repos/acme/widgets/pulls",
    }


def test_more_open_work_than_the_limit_is_cut_and_marked_truncated(
    monkeypatch,
) -> None:
    transport = _Transport(
        {"issues": [[_issue(n) for n in range(1, 6)]], "pulls": [[_pull(9)]]}
    )
    _bind(monkeypatch, transport)
    outcome = _call({"limit": 3})
    result = outcome.result_payload
    assert [row["number"] for row in result["issues"]] == [1, 2, 3]
    assert result["truncated"] is True


def test_pages_are_followed_until_a_short_page(monkeypatch) -> None:
    full = [_issue(n, pull=n % 2 == 0) for n in range(1, handler.PAGE_SIZE + 1)]
    transport = _Transport({"issues": [full, [_issue(500)]], "pulls": [[]]})
    _bind(monkeypatch, transport)
    result = _call().result_payload
    assert len(result["issues"]) == handler.PAGE_SIZE // 2 + 1
    assert result["issues"][-1]["number"] == 500
    assert result["truncated"] is False
    pages = [req.query["page"] for req in transport.requests if "issues" in req.path]
    assert pages == ["1", "2"]


def test_a_page_cap_reached_before_the_list_ends_is_truncated(monkeypatch) -> None:
    only_pulls = [_issue(n, pull=True) for n in range(handler.PAGE_SIZE)]
    transport = _Transport(
        {"issues": [only_pulls] * (handler.MAX_PAGES + 2), "pulls": [[]]}
    )
    _bind(monkeypatch, transport)
    result = _call().result_payload
    assert result["issues"] == []
    assert result["truncated"] is True
    issue_reads = [req for req in transport.requests if "issues" in req.path]
    assert len(issue_reads) == handler.MAX_PAGES


@pytest.mark.parametrize("limit", [0, handler.MAX_LIMIT + 1])
def test_limit_outside_its_range_is_an_invalid_payload(monkeypatch, limit) -> None:
    _bind(monkeypatch, _Transport({}))
    outcome = _call({"limit": limit})
    assert not outcome.primary_success
    assert outcome.error.code == "invalid_payload"


def test_a_project_without_a_bound_repository_refuses_by_name(monkeypatch) -> None:
    def missing(project, *, required_permissions):
        raise project_github_auth.MissingRepoBinding(
            project, f"project '{project}' is not bound to a GitHub App repository"
        )

    transport = _Transport({})
    _bind(monkeypatch, transport, resolve=missing)
    outcome = _call()
    assert not outcome.primary_success
    assert outcome.error.code == handler.BINDING_MISSING_CODE
    assert "missing_repo_binding" in outcome.error.message
    assert "yoke setup" in outcome.error.message
    assert "list open work from the forge yourself" in outcome.error.message
    assert transport.requests == []


def test_a_missing_permission_keeps_the_project_auth_repair(monkeypatch) -> None:
    def missing(project, *, required_permissions):
        raise project_github_auth.MissingPermission(
            project, "binding is missing permissions: issues"
        )

    _bind(monkeypatch, _Transport({}), resolve=missing)
    outcome = _call()
    assert outcome.error.code == "project_auth_error"
    assert "approve missing App permissions" in outcome.error.message


def test_a_github_auth_refusal_names_the_scope_and_never_the_token(
    monkeypatch,
) -> None:
    error = RestAuthError(f"HTTP 403: Resource not accessible {TOKEN}", status=403)
    _bind(monkeypatch, _Transport({}, error=error))
    outcome = _call()
    assert outcome.error.code == "rest_auth_error"
    assert "Issues: read and Pull requests: read" in outcome.error.message
    assert "HTTP 403" in outcome.error.message
    assert TOKEN not in outcome.error.message


def test_registration_is_a_floored_claim_free_project_read() -> None:
    (entry,) = handler.REGISTRATIONS
    assert entry["function_id"] == "github.open_work.list"
    assert entry["side_effects"] == []
    assert entry["claim_required_kind"] is None
    assert entry["minimum_serving_version"] == "next-release"
    assert FUNCTION_MINIMUM_SERVING_VERSIONS[handler.FUNCTION_ID] == "next-release"
    spec = classify(handler.FUNCTION_ID, side_effects=False, project_permission=None)
    # Classified as a project read, so it is served by the control plane
    # rather than falling back to the caller's machine.
    assert spec == classify(
        "github.merge_queue.readiness", side_effects=False, project_permission=None
    )
    assert spec.scope == PROJECT
