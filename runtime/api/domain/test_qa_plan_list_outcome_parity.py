"""Plan pages pick each plan's latest attempt exactly as the ranked history read did."""

from datetime import datetime, timedelta, timezone
import random

from runtime.api.fixtures.backlog_inserts import insert_item
from runtime.api.fixtures.backlog_qa_inserts import insert_qa_requirement, insert_qa_run
from runtime.api.fixtures.pg_testdb import test_database
from runtime.api.tools.read_query_profile import CountedConnection
from yoke_core.domain.db_helpers import query_rows
from yoke_core.domain.qa_execution_proof import qa_run_outcome
from yoke_core.domain.qa_latest_execution import latest_execution_id_sql
from yoke_core.domain.qa_obligation_settlement import (
    unanswered_attempt_sql,
    unretracted_requirement_sql,
)
from yoke_core.domain.qa_plan_list_reads import list_plans

BASE = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _ranked_history(conn, plan_ids):
    """Every live answered requirement ranked per plan: the reference answer."""
    markers = ",".join("%s" for _ in plan_ids)
    rows = query_rows(
        conn,
        "SELECT * FROM (SELECT q.plan_id, q.id, q.waived_at, r.verdict, "
        "r.verdict_reason, r.case_outcome, "
        "COALESCE(r.completed_at, r.created_at, q.created_at) AS happened_at, "
        "ROW_NUMBER() OVER (PARTITION BY q.plan_id ORDER BY "
        "COALESCE(r.completed_at, r.created_at, q.created_at) DESC, q.id DESC) AS position "
        f"FROM qa_requirements q LEFT JOIN qa_runs r ON r.id=({latest_execution_id_sql('q.id')}) "
        f"WHERE q.plan_id IN ({markers}) AND {unretracted_requirement_sql(conn, 'q')} "
        f"AND {unanswered_attempt_sql(conn, 'q')}) latest WHERE position=1",
        tuple(plan_ids),
    )
    return {int(row["plan_id"]): row for row in rows}


def _seed_history(conn, plan_count=12, per_plan=30):
    item_id = int(insert_item(conn, title="Plan history")["id"])
    rng = random.Random(4060)
    plan_ids = []
    for index in range(plan_count):
        plan_ids.append(
            int(
                conn.execute(
                    "INSERT INTO qa_plans(project_id,slug,name,created_at,updated_at) "
                    "VALUES (1,%s,%s,%s,%s) RETURNING id",
                    (f"history-{index:02d}", f"History {index}", BASE, BASE),
                ).fetchone()[0]
            )
        )
    for plan_id in plan_ids[:-1]:  # The last plan has no requirements at all.
        earlier = []
        for n in range(per_plan):
            created = BASE + timedelta(minutes=rng.randrange(0, 40))
            extra = {}
            shape = rng.random()
            if shape < 0.1:
                extra["retracted_at"] = created
            elif shape < 0.2 and earlier:
                extra["superseded_by_requirement_id"] = rng.choice(earlier)
            elif shape < 0.3 and earlier:
                extra["replacement_requirement_id"] = rng.choice(earlier)
            elif shape < 0.4:
                extra["waived_at"] = created
            requirement_id = int(
                insert_qa_requirement(
                    conn,
                    item_id=item_id,
                    plan_id=plan_id,
                    plan_case_key=f"case-{n}",
                    qa_kind="plan_case",
                    created_at=created,
                    **extra,
                )["id"]
            )
            earlier.append(requirement_id)
            for _ in range(rng.randrange(0, 4)):  # Some never ran.
                # Coarse minutes force equal instants, so the id tie-break decides.
                started = BASE + timedelta(minutes=rng.randrange(0, 40))
                verdict = rng.choice(["pass", "fail", "error", None])
                insert_qa_run(
                    conn,
                    qa_requirement_id=requirement_id,
                    qa_kind="plan_case",
                    verdict=verdict,
                    verdict_reason=f"run for {requirement_id}",
                    created_at=started,
                    started_at=None if rng.random() < 0.05 else started,
                    completed_at=(
                        started + timedelta(minutes=rng.randrange(0, 3))
                        if verdict
                        else None
                    ),
                )
    return plan_ids


def test_page_outcomes_match_ranked_history_read():
    with test_database() as conn:
        plan_ids = _seed_history(conn)
        reference = _ranked_history(conn, plan_ids)
        listed = {
            row["id"]: row
            for row in list_plans(conn, project="yoke", full=True)
            if row["id"] in plan_ids
        }
        paged = {
            row["id"]: row
            for offset in range(0, len(plan_ids) + 1, 5)
            for row in list_plans(conn, project="yoke", limit=5, offset=offset)
            if row["id"] in plan_ids
        }
    assert set(listed) == set(paged) == set(plan_ids)
    assert len(reference) == len(plan_ids) - 1
    for plan_id in plan_ids:
        expected = reference.get(plan_id)
        outcome = qa_run_outcome(expected) if expected is not None else None
        at = expected["happened_at"] if expected is not None else None
        assert listed[plan_id]["last_outcome"] == paged[plan_id]["last_outcome"] == outcome
        assert listed[plan_id]["last_at"] == paged[plan_id]["last_at"] == at
        assert listed[plan_id]["last_verdict_reason"] == (
            expected["verdict_reason"] if expected is not None else None
        )


def _page_query_count(per_plan):
    with test_database() as conn:
        _seed_history(conn, plan_count=6, per_plan=per_plan)
        counted = CountedConnection(conn)
        assert len(list_plans(counted, project="yoke", limit=5)) == 5
        return sum(counted.counts.values())


def test_page_query_count_does_not_grow_with_history():
    assert _page_query_count(per_plan=0) == _page_query_count(per_plan=40)
