"""Coverage for ``sync_item`` — single-issue and epic dispatch paths.

Covers create + reuse paths both using ``select_body_for_github``,
the transitive ``ProjectGithubAuthError`` catch, and create + reuse
regressions exercising the shared compact-mirror contract.

Tests mock the typed ``github_rest.create_issue`` / ``list_issues`` surfaces
directly (no argv shapes).
"""

from __future__ import annotations

import io
from unittest.mock import ANY, patch

from runtime.api.backlog_github_sync_test_helpers import (
    GH_PATCH,
    make_db as _make_db,
)
from runtime.api.conftest import insert_epic_task, insert_item

# Import the umbrella module FIRST so its transitive re-export chain
# completes before any sibling-specific submodule attempts to import it.
from yoke_core.domain import backlog_github_sync  # noqa: I001
from yoke_core.domain import backlog_github_item_create as item_create


from runtime.api.backlog_github_sync_test_helpers import (
    ITEM_CREATE_PATCH as _CREATE_PATCH,
    ITEM_DEDUP_PATCH as _DEDUP_PATCH,
    fake_issue as _fake_issue,
    item_auth_resolver as _ok_resolver,
)


class TestSyncItem:
    def test_already_synced_updates_labels_and_body(self):
        db = _make_db()
        insert_item(
            db,
            id=20,
            workflow_id="issue",
            status="idea",
            project="externalwebapp",
            github_issue="#100",
        )
        stdout = io.StringIO()
        with (
            patch.object(
                item_create,
                "resolve_project_github_auth",
                side_effect=_ok_resolver,
            ),
            patch(f"{GH_PATCH}.sync_labels", return_value=0) as mock_labels,
            patch(f"{GH_PATCH}.sync_body", return_value=0) as mock_body,
        ):
            rc = backlog_github_sync.sync_item("EXT-20", conn=db, stdout=stdout)
        assert rc == 0
        mock_labels.assert_called_once()
        mock_body.assert_called_once()
        assert "already synced" in stdout.getvalue()
        db.close()

    def test_already_synced_epic_also_syncs_child_tasks(self):
        db = _make_db()
        insert_item(
            db,
            id=21,
            workflow_id="epic",
            status="implementing",
            project="externalwebapp",
            github_issue="#100",
        )
        insert_epic_task(db, epic_id=21, task_num=1, title="Task 1", status="planned")
        stdout = io.StringIO()
        with (
            patch.object(
                item_create,
                "resolve_project_github_auth",
                side_effect=_ok_resolver,
            ),
            patch(f"{GH_PATCH}.sync_labels", return_value=0) as mock_labels,
            patch(f"{GH_PATCH}.sync_body", return_value=0) as mock_body,
            patch(
                f"{GH_PATCH}.epic_task_sync.sync_epic_tasks", return_value=0
            ) as mock_task_sync,
        ):
            rc = backlog_github_sync.sync_item("EXT-21", conn=db, stdout=stdout)
        assert rc == 0
        mock_labels.assert_called_once()
        mock_body.assert_called_once()
        mock_task_sync.assert_called_once_with(
            "EXT-21", conn=db, stdout=stdout, stderr=ANY
        )
        db.close()

    def test_creates_new_issue(self):
        db = _make_db()
        insert_item(
            db,
            id=20,
            workflow_id="issue",
            status="idea",
            priority="high",
            project="externalwebapp",
            spec="Test body content",
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
                return_value=_fake_issue(number=999),
            ),
            patch(
                "yoke_core.domain.backlog_github_item_create._regenerate_md",
            ),
            patch(
                "yoke_core.domain.backlog_github_item_create._ensure_label",
            ),
        ):
            rc = backlog_github_sync.sync_item("EXT-20", conn=db, stdout=stdout)

        assert rc == 0
        gh_issue = db.execute(
            "SELECT github_issue FROM items WHERE id = 20"
        ).fetchone()[0]
        assert gh_issue == "#999"
        notice = "Synced: EXT-20 → GitHub issue #999: "
        assert notice + _fake_issue(number=999).html_url in stdout.getvalue()
        db.close()

    def test_create_without_html_url_prints_host_neutral_reference(self):
        db = _make_db()
        insert_item(
            db,
            id=20,
            workflow_id="issue",
            status="idea",
            project="externalwebapp",
            spec="Test body content",
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
                return_value=_fake_issue(number=999, html_url=""),
            ),
            patch(
                "yoke_core.domain.backlog_github_item_create._regenerate_md",
            ),
            patch(
                "yoke_core.domain.backlog_github_item_create._ensure_label",
            ),
        ):
            rc = backlog_github_sync.sync_item("EXT-20", conn=db, stdout=stdout)
        assert rc == 0
        output = stdout.getvalue()
        assert "\n#999\n" in output
        assert "https://github.com/org/externalwebapp/issues/999" not in output
        db.close()

    def test_creates_new_epic_issue_and_syncs_child_tasks(self):
        db = _make_db()
        insert_item(
            db,
            id=22,
            workflow_id="epic",
            status="planning",
            priority="high",
            project="externalwebapp",
            spec="Epic body content",
        )
        insert_epic_task(db, epic_id=22, task_num=1, title="Task 1", status="planned")
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
                return_value=_fake_issue(number=1001),
            ),
            patch(
                "yoke_core.domain.backlog_github_item_create._regenerate_md",
            ),
            patch(
                "yoke_core.domain.backlog_github_item_create._ensure_label",
            ),
            patch(
                f"{GH_PATCH}.epic_task_sync.sync_epic_tasks", return_value=0
            ) as mock_task_sync,
        ):
            rc = backlog_github_sync.sync_item("EXT-22", conn=db, stdout=stdout)

        assert rc == 0
        gh_issue = db.execute(
            "SELECT github_issue FROM items WHERE id = 22"
        ).fetchone()[0]
        assert gh_issue == "#1001"
        mock_task_sync.assert_called_once_with(
            "EXT-22", conn=db, stdout=stdout, stderr=ANY
        )
        db.close()

    # Dedup behavior — exact-prefix reuse, fuzzy non-reuse, malformed-JSON
    # fallthrough — is exercised in runtime/api/test_github_dedup.py.

    def test_dry_run_skips(self):
        db = _make_db()
        insert_item(
            db, id=20, workflow_id="issue", status="idea", project="externalwebapp"
        )
        stdout = io.StringIO()
        with (
            patch.object(
                item_create,
                "resolve_project_github_auth",
                side_effect=_ok_resolver,
            ),
            patch.object(backlog_github_sync, "_dry_run", return_value=True),
        ):
            rc = backlog_github_sync.sync_item("EXT-20", conn=db, stdout=stdout)
        assert rc == 0
        assert "DRY-RUN" in stdout.getvalue()
        db.close()

    def test_missing_item_returns_error(self):
        db = _make_db()
        stderr = io.StringIO()
        rc = backlog_github_sync.sync_item("EXT-999", conn=db, stderr=stderr)
        assert rc == 1
        # The token resolved to nothing, so the error echoes what was typed.
        assert "no item for 'EXT-999'" in stderr.getvalue()
        db.close()

    def test_creates_new_issue_renders_owner_label(self):
        """A numeric source/owner renders to the actor's name and
        contributes ``source:`` / ``owner:`` labels to the create payload.
        The raw integer must not appear in any label argument."""
        from yoke_core.domain.actors import resolve_actors_by_name, seed_system_actor

        db = _make_db()
        (local_human,) = resolve_actors_by_name(db, "ben")
        sync_worker = seed_system_actor(db, "sync-worker")

        insert_item(
            db,
            id=23,
            workflow_id="issue",
            status="idea",
            priority="medium",
            project="externalwebapp",
            spec="Owner label test",
            source=str(local_human),
            owner=str(sync_worker),
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
                return_value=_fake_issue(number=777),
            ) as create_issue,
            patch(
                "yoke_core.domain.backlog_github_item_create._regenerate_md",
            ),
            patch(
                "yoke_core.domain.backlog_github_item_create._ensure_label",
            ),
        ):
            rc = backlog_github_sync.sync_item("EXT-23", conn=db, stdout=stdout)

        assert rc == 0
        create_issue.assert_called_once()
        labels = create_issue.call_args.kwargs["labels"]
        assert "source:ben" in labels
        assert "owner:sync-worker" in labels
        assert f"source:{local_human}" not in labels
        assert f"owner:{sync_worker}" not in labels
        db.close()
