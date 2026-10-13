"""Creation payloads and compact bodies define issue adoption identity."""

import io
from unittest.mock import Mock

import pytest

from yoke_core.domain import github_rest
from yoke_core.domain import epic_task_sync_github_create as epic
from yoke_core.domain.github_rest_issues import _parse_issue


@pytest.mark.parametrize("body", ["Body", "different body"])
def test_task_requires_full_content(monkeypatch, body):
    monkeypatch.setattr(
        epic.github_rest,
        "list_issues",
        lambda **_: [github_rest.Issue(7, "[TEST-1] 001 Task", "OPEN", body=body)],
    )
    create = Mock(return_value=github_rest.Issue(8, "Created", "OPEN"))
    monkeypatch.setattr(epic.github_rest, "create_issue", create)
    result = epic._dedup_or_create_task_issue(
        backlog_id="TEST-1",
        issue_title="[TEST-1] 001 Task",
        task_body="Body",
        labels=[],
        gh_project="example",
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert result == ("7" if body == "Body" else "8")
    assert create.call_count == (0 if body == "Body" else 1)


def test_old_task_title_format_is_not_adopted(monkeypatch):
    monkeypatch.setattr(
        epic.github_rest,
        "list_issues",
        lambda **_: [github_rest.Issue(7, "[TEST-1] Task", "OPEN", body="Body")],
    )
    create = Mock(return_value=github_rest.Issue(8, "Created", "OPEN"))
    monkeypatch.setattr(epic.github_rest, "create_issue", create)
    assert (
        epic._dedup_or_create_task_issue(
            backlog_id="TEST-1",
            task_num_str="001",
            task_title="Task",
            issue_title="[TEST-1] 001 Task",
            task_body="Body",
            labels=[],
            gh_project="example",
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        == "8"
    )


def test_compact_payload_is_compared_and_created_once(monkeypatch):
    select = Mock(return_value=("Compact mirror", "compact"))
    monkeypatch.setattr(epic._budget, "select_body_for_github", select)
    monkeypatch.setattr(epic._budget, "emit_compact_notice", Mock())
    monkeypatch.setattr(
        epic.github_rest,
        "list_issues",
        lambda **_: [github_rest.Issue(7, "Title", "OPEN", body="Full body")],
    )
    create = Mock(return_value=github_rest.Issue(8, "Title", "OPEN"))
    monkeypatch.setattr(epic.github_rest, "create_issue", create)
    epic._resolve_issue_with_body_budget(
        project="example",
        title="Title",
        body="Full body",
        labels=[],
        item_id=1,
        item_fields={},
        conn=None,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    select.assert_called_once()
    assert create.call_args.kwargs["body"] == "Compact mirror"


def test_issue_parser_preserves_pull_request_kind():
    assert _parse_issue({"number": 7, "pull_request": {}}).is_pull_request
    assert not _parse_issue({"number": 7}).is_pull_request
