# ruff: noqa: F811
"""Landing ends coverage; delivery is clear and rework acquires new coverage."""

from contextlib import contextmanager

import pytest

from runtime.api.domain._path_claims_test_helpers import (
    conn,  # noqa: F401
    local_human,
    seed_item,
    seed_target,  # noqa: F401
)
from yoke_contracts.api.function_call import (
    ActorContext,
    FunctionCallRequest,
    TargetRef,
)
from yoke_contracts.timestamps import utc_now
from yoke_core.domain.handlers import claims_path_terminal, item_landings_ops
from yoke_core.domain.item_landings import ItemLanding, append_landing
from yoke_core.domain.item_landings_schema import ensure_item_landings_schema
from yoke_core.domain.path_claims import get_claim, register
from yoke_core.domain.path_claims_landing import (
    evaluate_rework_coverage,
    needs_rework_coverage,
    release_landed_claims,
)
from yoke_core.domain.path_claim_required_gate import evaluate_required_coverage
from yoke_core.domain.workflow_runtime import load_item_workflow_runtime


def _seed(conn):
    item_id = seed_item(conn, item_id=9901, status="release")
    target = seed_target(conn, path_string="src/component.py")
    claim_id = register(
        conn,
        actor_id=local_human(conn),
        item_id=item_id,
        integration_target="main",
        target_ids=[target],
    )
    ensure_item_landings_schema(conn)
    landing = ItemLanding(
        item_id=item_id,
        merge_sha="a" * 40,
        candidate_sha="b" * 40,
        target_branch="main",
        route="standalone",
        landed_at=utc_now(),
    )
    append_landing(conn, landing)
    conn.commit()
    return item_id, claim_id, target


def test_release_is_transactional_and_idempotent(conn):
    item_id, claim_id, _ = _seed(conn)
    assert release_landed_claims(conn, item_id=item_id) == [claim_id]
    assert get_claim(conn, claim_id)["release_reason"] == "landed"
    conn.rollback()
    assert get_claim(conn, claim_id)["state"] == "planned"
    release_landed_claims(conn, item_id=item_id)
    conn.commit()
    assert release_landed_claims(conn, item_id=item_id) == []


def test_delivery_exempt_and_rework_needs_fresh_coverage(conn):
    item_id, claim_id, target = _seed(conn)
    release_landed_claims(conn, item_id=item_id)
    conn.commit()
    assert evaluate_required_coverage(conn, item_id)["verdict"] == "pass"
    from yoke_core.domain.path_integrity_invariants_claim_coverage import (
        check_path_claim_coverage,
    )

    assert check_path_claim_coverage(conn, 1) == []
    runtime = load_item_workflow_runtime(conn, item_id)
    blocked = evaluate_rework_coverage(
        conn=conn, item_id=item_id, target_status="implementing", workflow=runtime
    )
    assert blocked["error_code"] == "GATE_PATH_CLAIM_REWORK_COVERAGE"
    assert "register" in blocked["error"]
    conn.execute("UPDATE items SET status='implementing' WHERE id=%s", (item_id,))
    assert evaluate_required_coverage(conn, item_id)["verdict"] == "block"
    assert needs_rework_coverage(conn, item_id)
    assert check_path_claim_coverage(conn, 1)[0][0] == item_id
    fresh = register(
        conn,
        actor_id=local_human(conn),
        item_id=item_id,
        integration_target="main",
        target_ids=[target],
    )
    assert fresh != claim_id
    assert not needs_rework_coverage(conn, item_id)
    assert evaluate_required_coverage(conn, item_id)["verdict"] == "pass"


@pytest.mark.parametrize("action", ["release", "cancel"])
def test_terminal_handler_rejects_other_item_owner(conn, monkeypatch, action):
    item_id, claim_id, _ = _seed(conn)

    @contextmanager
    def connected():
        yield conn

    monkeypatch.setattr("yoke_core.domain.db_helpers.connect", connected)
    request = FunctionCallRequest(
        function=f"claims.path.{action}",
        actor=ActorContext(session_id="holder"),
        target=TargetRef(kind="item", item_id=item_id + 1),
        payload={"claim_id": claim_id, "reason": "finished"},
    )
    result = getattr(claims_path_terminal, f"handle_{action}")(request)
    assert not result.primary_success
    assert result.error.code == "claim_owner_mismatch"
    assert get_claim(conn, claim_id)["state"] == "planned"


@pytest.mark.parametrize(
    "action,state", [("release", "released"), ("cancel", "cancelled")]
)
def test_terminal_handler_persists_and_retries(conn, monkeypatch, action, state):
    item_id, claim_id, _ = _seed(conn)

    @contextmanager
    def connected():
        yield conn

    monkeypatch.setattr("yoke_core.domain.db_helpers.connect", connected)
    request = FunctionCallRequest(
        function=f"claims.path.{action}",
        actor=ActorContext(session_id="holder"),
        target=TargetRef(kind="item", item_id=item_id),
        payload={"claim_id": claim_id, "reason": "finished"},
    )
    for _ in range(2):
        result = getattr(claims_path_terminal, f"handle_{action}")(request)
        assert result.primary_success
        assert result.result_payload["state"] == state
    assert get_claim(conn, claim_id)["state"] == state


def test_landing_handler_releases_before_commit(conn, monkeypatch):
    item_id, claim_id, _ = _seed(conn)

    @contextmanager
    def connected():
        yield conn

    monkeypatch.setattr(item_landings_ops, "_connect_rw", connected)
    monkeypatch.setattr(item_landings_ops, "release_for_landed_item", lambda *a, **k: 0)
    request = FunctionCallRequest(
        function="item_landings.record",
        actor=ActorContext(session_id="holder"),
        target=TargetRef(kind="item", item_id=item_id),
        payload={
            "merge_sha": "c" * 40,
            "candidate_sha": "b" * 40,
            "target_branch": "main",
            "route": "standalone",
            "landed_at": "2026-10-13T19:00:00Z",
        },
    )
    result = item_landings_ops.handle_record_item_landing(request)
    assert result.primary_success, result.error
    assert get_claim(conn, claim_id)["release_reason"] == "landed"


def test_replayed_landing_preserves_fresh_rework_claims(conn, monkeypatch):
    item_id, _, target = _seed(conn)
    release_landed_claims(conn, item_id=item_id)
    conn.commit()
    fresh = register(
        conn,
        actor_id=local_human(conn),
        item_id=item_id,
        integration_target="main",
        target_ids=[target],
    )

    @contextmanager
    def connected():
        yield conn

    monkeypatch.setattr(item_landings_ops, "_connect_rw", connected)
    monkeypatch.setattr(
        item_landings_ops, "release_for_landed_item", lambda *a, **k: None
    )
    request = FunctionCallRequest(
        function="item_landings.record",
        actor=ActorContext(session_id="holder"),
        target=TargetRef(kind="item", item_id=item_id),
        payload={
            "merge_sha": "a" * 40,
            "candidate_sha": "b" * 40,
            "target_branch": "main",
            "route": "standalone",
            "landed_at": "2026-10-13T19:00:00Z",
        },
    )
    result = item_landings_ops.handle_record_item_landing(request)
    assert result.primary_success
    assert result.result_payload["appended"] is False
    assert get_claim(conn, fresh)["state"] == "planned"


def test_shared_resolver_requires_rework_registration(conn, monkeypatch):
    from yoke_core.domain import path_claim_active_claim_lookup as lookup

    item_id, _, target = _seed(conn)
    release_landed_claims(conn, item_id=item_id)
    conn.commit()
    monkeypatch.setattr(lookup, "_current_item_for_session", lambda *a: item_id)
    monkeypatch.setattr(
        lookup, "_paths_for_item", lambda *a: {"worktree_path": "/repo/lane"}
    )
    scope = lookup.resolve_active_claim_for_session(conn=conn, session_id="holder")
    assert scope["state"] == "rework-coverage-required"
    fresh = register(
        conn,
        actor_id=local_human(conn),
        item_id=item_id,
        integration_target="main",
        target_ids=[target],
    )
    scope = lookup.resolve_active_claim_for_session(conn=conn, session_id="holder")
    assert scope["id"] == fresh
    assert scope["covered_paths"] == ["src/component.py"]
