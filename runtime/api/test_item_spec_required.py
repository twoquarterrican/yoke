# ruff: noqa: F811
"""Items are created with their spec; leftovers wait labelled "Needs a spec"."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from runtime.api.api_items_test_helpers import (
    make_client_fixture,
    make_test_db_fixture,
)
from runtime.api.backlog_mutations_test_helpers import (
    _conn,
    _patch_externals,
    tmp_db,  # noqa: F401 - pytest fixture re-export
)
from runtime.api.conftest import insert_item as insert_backlog_item
from runtime.api.engines._doctor_hc_db_full_test_helpers import _result, _run_hc
from runtime.api.frontier_test_helpers import insert_item, make_test_db
from yoke_contracts.api.function_call import (
    ActorContext,
    FunctionCallRequest,
    TargetRef,
)
from yoke_core.domain import backlog
from yoke_core.domain.frontier import compute_frontier
from yoke_core.domain.handlers.items_create import handle_item_create
from yoke_core.domain.item_spec_completeness import (
    item_needs_spec,
    missing_spec_refusal,
    needs_spec_reason,
    spec_is_title_only,
)
from yoke_core.engines.doctor_hc_meta_backlog import hc_items_needing_spec


@pytest.mark.parametrize(
    ("spec", "title_only"),
    [
        (None, True),
        ("", True),
        ("   \n", True),
        ("# Same shape", True),
        ("# Same shape\n", True),
        ("# Same shape\n\nThe board lists it; done when it shows.", False),
        ("Ship the export button.", False),
    ],
)
def test_title_only_classification(spec, title_only):
    assert spec_is_title_only("Same shape", spec) is title_only
    assert item_needs_spec({"title": "Same shape", "spec": spec}) is title_only
    assert (missing_spec_refusal("Same shape", spec) is not None) is title_only


def test_a_short_outcome_under_a_long_title_is_a_spec():
    title = "Make the export page download every visible column as CSV"
    assert spec_is_title_only(title, "Done when it opens.") is False
    assert spec_is_title_only(title, f"## {title}  ") is True


def test_refusal_names_the_code_and_the_repair():
    refusal = missing_spec_refusal("Title", "")
    assert refusal.startswith("spec_required: ")
    assert "--spec-file PATH" in refusal and "--stdin" in refusal


def _create(tmp_db, **overrides):
    kwargs = dict(
        project="yoke",
        title="Filed outcome",
        workflow="issue",
        entry_surface="harness_skill",
    )
    kwargs.update(overrides)
    with _patch_externals(), mock.patch.dict(os.environ, {"YOKE_DB": tmp_db}):
        return backlog.execute_create(**kwargs)


@pytest.mark.parametrize("workflow", ["issue", "dash", "task", "epic"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_every_workflow_refuses_a_title_only_create(tmp_db, workflow, dry_run):
    result = _create(tmp_db, workflow=workflow, spec="# Filed outcome", dry_run=dry_run)
    assert result["success"] is False
    assert result["error_code"] == "spec_required"
    assert "--spec-file PATH" in result["error"]


def test_create_with_a_spec_stores_it(tmp_db):
    spec = "The export button downloads a CSV; done when the file opens."
    result = _create(tmp_db, spec=spec)
    assert result["success"] is True
    from runtime.api.fixtures.file_test_db import connect_test_db

    conn = connect_test_db(tmp_db)
    try:
        row = conn.execute(
            "SELECT spec FROM items WHERE id = %s", (result["item_id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == spec


@pytest.mark.parametrize("workflow", ["dash", "task", "issue", "epic"])
@pytest.mark.parametrize("spec", [None, "", " \n\t", "# Filed outcome"])
def test_items_create_refuses_without_allocating_or_writing(tmp_db, workflow, spec):
    payload = {
        "title": "Filed outcome",
        "workflow": workflow,
        "project": "yoke",
        "entry_surface": "cli" if workflow in ("dash", "task") else "harness_skill",
        "execution_instructions_considered": True,
    }
    if spec is not None:
        payload["spec"] = spec
    request = FunctionCallRequest(
        function="items.create",
        actor=ActorContext(session_id="title-only-test"),
        target=TargetRef(kind="global"),
        payload=payload,
    )
    before = _item_count(tmp_db)
    with (
        _patch_externals(),
        mock.patch.dict(os.environ, {"YOKE_DB": tmp_db}),
        mock.patch("yoke_core.domain.backlog_create_op._get_next_id") as next_id,
        mock.patch(
            "yoke_core.domain.backlog_create_op.allocate_project_sequence"
        ) as next_sequence,
    ):
        outcome = handle_item_create(request)

    assert outcome.primary_success is False
    assert outcome.error.code == "spec_required"
    assert "--spec-file PATH" in outcome.error.message
    next_id.assert_not_called()
    next_sequence.assert_not_called()
    assert _item_count(tmp_db) == before


def _item_count(db_path) -> int:
    conn = _conn(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    finally:
        conn.close()


def test_frontier_holds_a_title_only_item_labelled_needs_a_spec():
    conn = make_test_db()
    insert_item(conn, 50, title="Stale draft", status="idea", spec="# Stale draft")
    insert_item(conn, 51, title="Real idea", status="idea")
    insert_item(conn, 52, title="Empty spec", status="idea", spec="")
    conn.commit()

    result = compute_frontier(conn, project_scope=["yoke"])
    blocked = {fi.item_id: fi for fi in result.blocked}
    assert set(blocked) == {50, 52}
    assert [fi.item_id for fi in result.runnable] == [51]
    assert blocked[50].needs_spec is True
    assert blocked[50].blocked_reasons == [needs_spec_reason("YOK-50")]
    assert blocked[50].blocked_reasons[0].startswith("Needs a spec: YOK-50 ")


def test_doctor_lists_items_that_need_a_spec(test_db):
    insert_backlog_item(test_db, id=1, title="Left title only", spec="")
    insert_backlog_item(test_db, id=2, title="Has an outcome", spec="Done when shown.")
    insert_backlog_item(
        test_db, id=3, title="Past its first stage", status="implementing", spec=""
    )
    test_db.commit()

    result = _result(_run_hc(hc_items_needing_spec, test_db))
    assert result.result == "WARN"
    assert result.detail == f"- {needs_spec_reason('YOK-1')}"


def test_doctor_passes_when_every_item_has_a_spec(test_db):
    insert_backlog_item(test_db, id=1, title="Has an outcome", spec="Done when shown.")
    test_db.commit()

    assert _result(_run_hc(hc_items_needing_spec, test_db)).result == "PASS"


@pytest.fixture()
def api_db():
    yield from make_test_db_fixture()


@pytest.fixture()
def client(api_db):
    yield from make_client_fixture()


@pytest.mark.parametrize("spec", [None, "", "# Title only", "# Title only\n"])
def test_create_item_without_a_spec_is_refused(client, spec):
    body = {"title": "Title only", "workflow": "dash", "project": "yoke"}
    if spec is not None:
        body["spec"] = spec
    resp = client.post("/v1/items", json=body)
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "SPEC_REQUIRED"
    assert "--spec-file PATH" in error["message"]
    from yoke_core.domain import db_backend

    conn = db_backend.connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM items WHERE title = 'Title only'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == 0


def test_create_item_stores_its_spec(client):
    resp = client.post(
        "/v1/items",
        json={
            "title": "Born with a spec",
            "spec": "Agreed outcome: the board shows this item.",
            "workflow": "dash",
            "project": "yoke",
        },
    )
    assert resp.status_code == 201
    from yoke_core.domain import db_backend

    conn = db_backend.connect()
    try:
        row = conn.execute(
            "SELECT spec FROM items WHERE title = 'Born with a spec'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "Agreed outcome: the board shows this item."
