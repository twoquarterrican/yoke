"""Shipping shares authority reads at the observed release/member scale."""

from collections import Counter
from time import perf_counter

from runtime.api.domain.test_deployment_qa_stage_execution import (
    _complete_case,
    _plan,
    _seed_run,
    _stages,
)
from runtime.api.domain.test_deployment_qa_shared_plans import _attach, _fail
from yoke_core.domain.deployment_qa_run_acceptance import (
    current_item_qa,
    member_qa_standings,
)
from yoke_core.domain.deployment_qa_stage_materialization import (
    materialize_deployment_qa_stage,
)
from yoke_core.domain.deployment_qa_stage_gate import deployment_qa_stage_status
from yoke_core.domain.qa_plan_execution_state import begin_plan_execution


class CountedConnection:
    def __init__(self, conn):
        self.conn = conn
        self.queries = Counter()

    def execute(self, sql, params=()):
        self.queries[sql] += 1
        return self.conn.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self.conn, name)


def test_member_presentation_shares_reads_without_reusing_next_request(test_db):
    plan = _plan(test_db, "shipping-shared-check")
    stages = _stages(plan)
    stages[1].pop("cases")
    subjects = []
    requirement_ids = []
    for index in range(12):
        run_id = f"shipping-run-{index}"
        count = 17 if index < 2 else 16
        members = tuple(20000 + index * 20 + n for n in range(count))
        _seed_run(test_db, run_id=run_id, stages=stages, members=members)
        for member in members:
            _attach(test_db, member, plan)
            subjects.append((run_id, member, "item-qa"))
        materialize_deployment_qa_stage(
            test_db,
            deployment_run_id=run_id,
            deployment_stage="item-qa",
            deployment_member_item_id=members[0],
        )
        execution = begin_plan_execution(
            test_db,
            deployment_run_id=run_id,
            deployment_stage="item-qa",
            deployment_member_item_id=members[0],
            actor_id="2",
            session_id="shipping-read",
        )
        requirement_ids.append(_complete_case(test_db, execution))
        assert deployment_qa_stage_status(
            test_db,
            run_id=run_id,
            stage_name="item-qa",
            member_item_id=members[0],
        )["accepted"]
    assert len(subjects) == 194
    _fail(test_db, requirement_ids[-1])
    conn = CountedConnection(test_db)
    start = perf_counter()
    answers = member_qa_standings(conn, subjects)
    elapsed = perf_counter() - start
    assert len(answers) == 194
    assert sum(answer["state"] == "accepted" for answer in answers.values()) == 178
    assert all(
        answers[(run, member)]["state"] == "cases unresolved"
        for run, member, _ in subjects[-16:]
    )
    baseline = CountedConnection(test_db)
    before = perf_counter()
    for run, member, stage in subjects:
        expected = current_item_qa(
            baseline, run_id=run, item_id=member, current_stage=stage
        )
        assert answers[(run, member)] == {
            "state": expected.state,
            "stage": expected.stage,
            "reason": expected.reason,
            "failed_requirement_ids": list(expected.failed_requirement_ids),
        }
    before_elapsed = perf_counter() - before
    assert sum(conn.queries.values()) < sum(baseline.queries.values())
    run_reads = sum(n for sql, n in conn.queries.items() if "o.id AS tenant_id" in sql)
    member_reads = sum(
        n
        for sql, n in conn.queries.items()
        if "SELECT dri.item_id,dri.requirement_snapshot" in sql
    )
    receipt_reads = sum(
        n
        for sql, n in conn.queries.items()
        if "SELECT id FROM deployment_stage_receipts" in sql
    )
    assert (run_reads, member_reads, receipt_reads) == (12, 12, 12)
    print(
        f"Shipping: runs=12 members=194 queries={sum(conn.queries.values())} "
        f"run_reads={run_reads} member_reads={member_reads} receipt_reads={receipt_reads} "
        f"elapsed_seconds={elapsed:.3f} "
        f"unbatched_queries={sum(baseline.queries.values())} "
        f"unbatched_seconds={before_elapsed:.3f}"
    )
    # A later request must read a changed verdict, rather than reuse a cached pass.
    _fail(test_db, requirement_ids[0])
    changed = member_qa_standings(conn, subjects[:17])
    assert all(answer["state"] == "cases unresolved" for answer in changed.values())
