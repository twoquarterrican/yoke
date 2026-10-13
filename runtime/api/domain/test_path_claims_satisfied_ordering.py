# ruff: noqa: F401, F811
"""Completed ordering stops serializing overlapping claims without rewriting edges."""

import pytest

from runtime.api.domain._path_claims_test_helpers import (
    conn,
    local_human,
    seed_item,
    seed_target,
    seed_claim,
)
from yoke_core.domain.path_claims_dependency_resolver_coordination import (
    CoordinationClassification,
    classify_inter_item_edges,
    has_forward_serial_edge,
)
from yoke_core.domain.path_claims_overlap import classify_overlap, OverlapClassification


@pytest.mark.parametrize("gate_point", ["activation", "integration", "closure"])
def test_merged_fact_stops_serializing_active_holder(conn, gate_point):
    blocker = seed_item(conn, item_id=9901, status="implementing")
    dependent = seed_item(conn, item_id=9902, status="idea")
    target = seed_target(conn, path_string="src/shared.py")
    holder = seed_claim(conn, item_id=blocker, target_id=target, state="active")
    conn.execute(
        "INSERT INTO item_dependencies (dependent_item_id,blocking_item_id,gate_point,satisfaction) "
        "VALUES (%s,%s,%s,'fact:merged')",
        (dependent, blocker, gate_point),
    )
    conn.commit()

    def classification():
        return classify_inter_item_edges(
            conn,
            candidate_claim_id=None,
            candidate_item_id=dependent,
            blocking_claim_id=holder,
        )

    assert classification() is CoordinationClassification.HAS_SERIAL
    assert has_forward_serial_edge(
        conn, dependent_item_id=dependent, blocking_item_id=blocker
    )
    conn.execute(
        "UPDATE items SET merged_at='2026-10-13T18:20:00Z' WHERE id=%s", (blocker,)
    )
    conn.commit()
    assert classification() is CoordinationClassification.COORDINATION_ONLY
    assert not has_forward_serial_edge(
        conn, dependent_item_id=dependent, blocking_item_id=blocker
    )
    assert (
        classify_overlap(
            conn,
            integration_target="main",
            target_ids=[target],
            candidate_item_id=dependent,
        )
        is OverlapClassification.NONE
    )
    assert (
        conn.execute("SELECT gate_point FROM item_dependencies").fetchone()[0]
        == gate_point
    )
    # Reopening invalidates status satisfaction but keeps a recorded merge fact.
    conn.execute("UPDATE items SET status='implementing' WHERE id=%s", (blocker,))
    assert classification() is CoordinationClassification.COORDINATION_ONLY


def test_another_unmet_edge_keeps_pair_serial(conn):
    blocker = seed_item(conn, item_id=9901, status="release")
    dependent = seed_item(conn, item_id=9902)
    target = seed_target(conn, path_string="src/shared.py")
    holder = seed_claim(conn, item_id=blocker, target_id=target, state="active")
    conn.execute(
        "UPDATE items SET merged_at='2026-10-13T18:20:00Z' WHERE id=%s", (blocker,)
    )
    for satisfaction in ("fact:merged", "status:done"):
        conn.execute(
            "INSERT INTO item_dependencies (dependent_item_id,blocking_item_id,gate_point,satisfaction) "
            "VALUES (%s,%s,'activation',%s)",
            (dependent, blocker, satisfaction),
        )
    conn.commit()
    assert (
        classify_inter_item_edges(
            conn,
            candidate_claim_id=None,
            candidate_item_id=dependent,
            blocking_claim_id=holder,
        )
        is CoordinationClassification.HAS_SERIAL
    )
    conn.execute("UPDATE items SET status='done' WHERE id=%s", (blocker,))
    conn.commit()
    assert (
        classify_inter_item_edges(
            conn,
            candidate_claim_id=None,
            candidate_item_id=dependent,
            blocking_claim_id=holder,
        )
        is CoordinationClassification.COORDINATION_ONLY
    )


def test_blocked_claim_can_activate_after_recorded_merge_without_holder_release(conn):
    from yoke_core.domain.path_claims import register, activate, get_claim

    blocker = seed_item(conn, item_id=9901, status="implementing")
    dependent = seed_item(conn, item_id=9902)
    target = seed_target(conn, path_string="src/shared.py")
    holder = seed_claim(conn, item_id=blocker, target_id=target, state="active")
    conn.execute(
        "INSERT INTO item_dependencies (dependent_item_id,blocking_item_id,gate_point,satisfaction) "
        "VALUES (%s,%s,'activation','fact:merged')",
        (dependent, blocker),
    )
    conn.commit()
    candidate = register(
        conn,
        actor_id=local_human(conn),
        item_id=dependent,
        integration_target="main",
        target_ids=[target],
        upstream_claim_id=holder,
    )
    assert get_claim(conn, candidate)["state"] == "blocked"
    conn.execute(
        "UPDATE items SET merged_at='2026-10-13T18:20:00Z' WHERE id=%s", (blocker,)
    )
    conn.commit()
    activate(conn, claim_id=candidate, base_commit_sha="a" * 40)
    assert get_claim(conn, candidate)["state"] == "active"
    assert get_claim(conn, holder)["state"] == "active"
