"""Compact issue mirroring and auth refusal regressions."""

from __future__ import annotations

import io
from unittest.mock import patch

from runtime.api.backlog_github_sync_test_helpers import (
    GH_PATCH,
    ITEM_CREATE_PATCH as _CREATE_PATCH,
    ITEM_DEDUP_PATCH as _DEDUP_PATCH,
    fake_issue as _fake_issue,
    item_auth_resolver as _ok_resolver,
    make_db as _make_db,
)
from runtime.api.conftest import insert_item
from yoke_core.domain import backlog_github_sync
from yoke_core.domain import backlog_github_body_budget as body_budget
from yoke_core.domain import backlog_github_item_create as item_create
from yoke_core.domain.project_github_auth import MissingRepoBinding


class TestSyncItemCompactMirror:
    def test_create_uses_compact_mirror_for_oversized(self):
        """Create path picks compact mirror when full body is
        oversized; the body string passed to ``create_issue`` fits under the
        budget."""
        db = _make_db()
        huge_spec = "a" * (body_budget.GITHUB_BODY_BUDGET_BYTES + 100)
        insert_item(
            db,
            id=30,
            workflow_id="issue",
            status="idea",
            project="externalwebapp",
            priority="medium",
            spec=huge_spec,
        )
        stdout = io.StringIO()

        with (
            patch.object(
                item_create,
                "resolve_project_github_auth",
                side_effect=_ok_resolver,
            ),
            patch(f"{GH_PATCH}._github_auth_available", return_value=True),
            patch(
                _DEDUP_PATCH,
                return_value=[],
            ),
            patch(
                _CREATE_PATCH,
                return_value=_fake_issue(number=901),
            ) as create_issue,
            patch(
                "yoke_core.domain.backlog_github_item_create._regenerate_md",
            ),
            patch(
                "yoke_core.domain.backlog_github_item_create._ensure_label",
            ),
        ):
            rc = backlog_github_sync.sync_item("EXT-30", conn=db, stdout=stdout)

        assert rc == 0
        create_issue.assert_called_once()
        body = create_issue.call_args.kwargs["body"]
        assert len(body.encode("utf-8")) <= body_budget.GITHUB_BODY_BUDGET_BYTES
        db.close()

    def test_reuse_inherits_compact_mirror(self):
        """Reuse path delegates body sync to ``sync_body`` which
        owns the same body-budget contract."""
        db = _make_db()
        huge_spec = "a" * (body_budget.GITHUB_BODY_BUDGET_BYTES + 100)
        insert_item(
            db,
            id=31,
            workflow_id="issue",
            status="idea",
            project="externalwebapp",
            github_issue="#205",
            spec=huge_spec,
        )
        stdout = io.StringIO()
        # Mock sync_body so we only assert that the reuse path delegated
        # to it; the compact-mirror behavior of sync_body is exercised in
        # test_backlog_github_sync_body_title.
        with (
            patch.object(
                item_create,
                "resolve_project_github_auth",
                side_effect=_ok_resolver,
            ),
            patch(f"{GH_PATCH}.sync_labels", return_value=0),
            patch(
                f"{GH_PATCH}.sync_body",
                return_value=0,
            ) as mock_body,
        ):
            rc = backlog_github_sync.sync_item("EXT-31", conn=db, stdout=stdout)

        assert rc == 0
        mock_body.assert_called_once()
        db.close()

    def test_auth_failure_short_circuits_create(self):
        """``sync_item`` short-circuits on resolver error
        before any dedup search, label seeding, or REST call."""
        db = _make_db()
        insert_item(
            db,
            id=32,
            workflow_id="issue",
            status="idea",
            project="externalwebapp",
            spec="body",
        )
        stderr = io.StringIO()

        def raise_missing_binding(*a, **kw):
            raise MissingRepoBinding("externalwebapp", "repository is not bound")

        with (
            patch.object(
                item_create,
                "resolve_project_github_auth",
                side_effect=raise_missing_binding,
            ),
            patch(_DEDUP_PATCH) as dedup,
            patch(_CREATE_PATCH) as create_issue,
        ):
            rc = backlog_github_sync.sync_item("EXT-32", conn=db, stderr=stderr)

        assert rc == 1
        dedup.assert_not_called()
        create_issue.assert_not_called()
        assert "MissingRepoBinding" in stderr.getvalue()
        db.close()
