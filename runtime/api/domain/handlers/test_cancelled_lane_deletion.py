"""The cancelled-lane record writes a cancelled item's Progress Log only."""

from __future__ import annotations

from contextlib import nullcontext

from runtime.api.fixtures.backlog_inserts import insert_item, insert_item_worktree
from yoke_contracts.api.function_call import (
    ActorContext,
    FunctionCallRequest,
    TargetRef,
)
from yoke_core.domain import db_helpers, item_field_transform
from yoke_core.domain.handlers import cancelled_lane_deletion as handler
from yoke_core.domain.item_field_transform import TransformResult

HEAD = "a" * 40
REMOTE = "b" * 40


def _request(item_id: int, lanes: list[dict]) -> FunctionCallRequest:
    return FunctionCallRequest(
        function="item_worktrees.cancelled_lanes.record",
        actor=ActorContext(session_id="cancelled-lane-record-test"),
        target=TargetRef(kind="item", item_id=item_id),
        payload={"lanes": lanes, "machine": "laptop"},
    )


def _wire(monkeypatch, test_db) -> list[dict]:
    appended: list[dict] = []
    monkeypatch.setattr(db_helpers, "connect", lambda: nullcontext(test_db))

    def append(**kwargs):
        appended.append(kwargs)
        return TransformResult(success=True, operation="section_append", changed=True)

    monkeypatch.setattr(item_field_transform, "section_append", append)
    return appended


def test_cancelled_item_records_every_deleted_lane_sha(test_db, monkeypatch):
    insert_item(test_db, id=951, status="cancelled")
    insert_item_worktree(test_db, item_id=951, branch="YOK-951", state="released")
    appended = _wire(monkeypatch, test_db)

    outcome = handler.handle_record(
        _request(
            951,
            [
                {
                    "branch": "YOK-951",
                    "worktree_path": "/repo/.worktrees/YOK-951",
                    "head_sha": HEAD,
                    "remote_head_sha": REMOTE,
                    "uncommitted_paths": 2,
                    "kept": ["remote branch origin/YOK-951 kept: delete refused"],
                }
            ],
        )
    )

    assert outcome.primary_success, outcome.error
    assert outcome.result_payload == {"item_id": 951, "lanes_recorded": 1}
    [entry] = appended
    assert entry["section"] == "Progress Log"
    assert entry["headline"] == "Cancelled lanes deleted"
    assert "on laptop" in entry["content"]
    assert f"head {HEAD}" in entry["content"]
    assert f"origin head {REMOTE}" in entry["content"]
    assert "2 uncommitted path(s) discarded" in entry["content"]
    assert "not deleted: remote branch origin/YOK-951 kept" in entry["content"]


def test_item_that_is_not_cancelled_is_refused(test_db, monkeypatch):
    insert_item(test_db, id=952, status="done")
    insert_item_worktree(test_db, item_id=952, branch="YOK-952", state="released")
    appended = _wire(monkeypatch, test_db)

    outcome = handler.handle_record(_request(952, [{"branch": "YOK-952"}]))

    assert not outcome.primary_success
    assert outcome.error.code == "item_not_cancelled_lane"
    assert "not cancelled" in outcome.error.message
    assert appended == []


def test_branch_the_item_never_owned_is_refused(test_db, monkeypatch):
    insert_item(test_db, id=953, status="cancelled")
    insert_item_worktree(test_db, item_id=953, branch="YOK-953", state="released")
    appended = _wire(monkeypatch, test_db)

    outcome = handler.handle_record(_request(953, [{"branch": "main"}]))

    assert not outcome.primary_success
    assert "no lane on branch(es) main" in outcome.error.message
    assert appended == []
