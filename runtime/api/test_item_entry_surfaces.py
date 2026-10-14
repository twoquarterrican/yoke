# ruff: noqa: F811
"""Coverage for typed workflow entry surfaces on item creation."""

from __future__ import annotations

import io
import os
from unittest import mock

import pytest

from runtime.api.api_items_test_helpers import (
    make_client_fixture,
    make_test_db_fixture,
)
from runtime.api.backlog_mutations_test_helpers import (
    _patch_externals,
    tmp_db,  # noqa: F401 - pytest fixture re-export
)
from yoke_core.domain import backlog, db_backend
from yoke_core.domain.item_entry_surface import (
    ITEM_ENTRY_SURFACE_ENV,
    MISSING_ENTRY_SURFACE_MESSAGE,
    enforce_item_entry_allowed,
    is_test_isolation,
    resolve_entry_surface,
)
from yoke_core.domain.workflow_runtime import builtin_workflow_runtime


@pytest.fixture()
def api_db():
    yield from make_test_db_fixture()


@pytest.fixture()
def client(api_db):
    yield from make_client_fixture()


class TestEntrySurfaceGate:
    def test_dry_run_allows_missing_surface(self, monkeypatch):
        monkeypatch.delenv(ITEM_ENTRY_SURFACE_ENV, raising=False)
        error = enforce_item_entry_allowed(
            workflow=builtin_workflow_runtime("issue"),
            dry_run=True,
        )
        assert error is None

    def test_allowed_explicit_surface(self, monkeypatch):
        monkeypatch.delenv(ITEM_ENTRY_SURFACE_ENV, raising=False)
        error = enforce_item_entry_allowed(
            workflow=builtin_workflow_runtime("issue"),
            entry_surface="harness_skill",
        )
        assert error is None

    def test_environment_surface_is_normalized(self, monkeypatch):
        monkeypatch.setenv(ITEM_ENTRY_SURFACE_ENV, " HARNESS_SKILL ")
        assert resolve_entry_surface() == "harness_skill"

    def test_workflow_rejects_disallowed_surface(self):
        error = enforce_item_entry_allowed(
            workflow=builtin_workflow_runtime("issue"),
            entry_surface="web_form",
        )
        assert error is not None
        assert "does not allow" in error

    def test_missing_surface_fails_closed(self, monkeypatch):
        monkeypatch.delenv(ITEM_ENTRY_SURFACE_ENV, raising=False)
        error = enforce_item_entry_allowed(
            workflow=builtin_workflow_runtime("issue"),
        )
        assert error == MISSING_ENTRY_SURFACE_MESSAGE

    def test_test_isolation_uses_active_postgres_authority(
        self,
        tmp_path,
        monkeypatch,
    ):
        token = str(tmp_path / "compatibility-token.db")
        monkeypatch.setenv(
            db_backend.PG_DSN_ENV,
            "host=/tmp/sock user=yoketest dbname=yoke_test_entry_surface",
        )
        assert is_test_isolation(token) is True
        monkeypatch.setenv(
            db_backend.PG_DSN_ENV,
            "host=/tmp/sock user=yoke dbname=yoke_prod",
        )
        assert is_test_isolation(token) is False
        assert is_test_isolation(None) is False


class TestExecuteCreateEntrySurface:
    def test_dry_run_works_without_surface(self, tmp_db, monkeypatch):
        monkeypatch.delenv(ITEM_ENTRY_SURFACE_ENV, raising=False)
        out = io.StringIO()
        with (
            _patch_externals(),
            mock.patch.dict(
                os.environ,
                {"YOKE_DB": tmp_db},
            ),
        ):
            result = backlog.execute_create(
                project="yoke",
                title="Dry run only",
                spec="Agreed outcome: the item shows on the board.",
                workflow="issue",
                dry_run=True,
                out=out,
            )
        assert result["success"] is True
        assert result.get("dry_run") is True

    def test_explicit_surface_allows_create(self, tmp_db, monkeypatch):
        monkeypatch.delenv(ITEM_ENTRY_SURFACE_ENV, raising=False)
        with (
            _patch_externals(),
            mock.patch.dict(
                os.environ,
                {"YOKE_DB": tmp_db},
            ),
        ):
            result = backlog.execute_create(
                project="yoke",
                title="Harness-created item",
                spec="Agreed outcome: the item shows on the board.",
                workflow="issue",
                entry_surface="harness_skill",
            )
        assert result["success"] is True

    def test_environment_surface_allows_create(self, tmp_db):
        with (
            _patch_externals(),
            mock.patch.dict(
                os.environ,
                {
                    "YOKE_DB": tmp_db,
                    ITEM_ENTRY_SURFACE_ENV: "harness_skill",
                },
            ),
        ):
            result = backlog.execute_create(
                project="yoke",
                title="Environment-routed item",
                spec="Agreed outcome: the item shows on the board.",
                workflow="issue",
            )
        assert result["success"] is True

    def test_missing_surface_blocks_when_test_bypass_is_disabled(
        self,
        tmp_db,
        monkeypatch,
    ):
        monkeypatch.delenv(ITEM_ENTRY_SURFACE_ENV, raising=False)
        monkeypatch.setattr(
            "yoke_core.domain.item_entry_surface.is_test_isolation",
            lambda _db_path: False,
        )
        with (
            _patch_externals(),
            mock.patch.dict(
                os.environ,
                {"YOKE_DB": tmp_db},
            ),
        ):
            result = backlog.execute_create(
                project="yoke",
                title="Unrouted item",
                workflow="issue",
            )
        assert result["success"] is False
        assert result["error"] == MISSING_ENTRY_SURFACE_MESSAGE


class TestCreateAdapters:
    def test_web_form_rejects_issue_workflow(self, client):
        response = client.post(
            "/v1/items",
            json={
                "title": "Web issue",
                "spec": "Agreed outcome for the web issue.",
                "workflow": "issue",
                "project": "yoke",
            },
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ENTRY_SURFACE_DENIED"

    def test_web_form_allows_dash_workflow(self, client):
        response = client.post(
            "/v1/items",
            json={
                "title": "Web dash",
                "spec": "Agreed outcome for the web dash.",
                "workflow": "dash",
                "project": "yoke",
            },
        )
        assert response.status_code == 201
        assert response.json()["workflow_id"] == "dash"
