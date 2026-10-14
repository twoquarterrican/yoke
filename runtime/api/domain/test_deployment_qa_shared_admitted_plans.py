"""Plans reaching members only through admitted requirements share like attachments."""

from runtime.api.domain.test_deployment_qa_admission_execution import (
    _original_requirement,
)
from runtime.api.domain.test_deployment_qa_stage_execution import (
    _plan,
    _seed_run,
    _stages,
)
from yoke_core.domain.deployment_qa_stage_materialization import (
    materialize_deployment_qa_stage,
)
from yoke_core.domain.deployment_requirement_snapshots import (
    requirement_selection,
    snapshot_member_requirements,
)

RUN = "run-shared-admitted-plans"
MEMBERS = (9911, 9912, 9913)


def _admit_plan_requirement(conn, member, plan_id):
    """Freeze one plan-owned requirement into the member's admission snapshot."""
    requirement_id = _original_requirement(conn, item_id=member, method_id="command")
    conn.execute(
        "UPDATE qa_requirements SET qa_kind='plan_case',plan_id=%s,"
        "plan_case_key='command-smoke',case_position=1,"
        'method_config=\'{"command": "true"}\' WHERE id=%s',
        (plan_id, requirement_id),
    )
    snapshot = snapshot_member_requirements(
        conn,
        run_id=RUN,
        item_id=member,
        selection_json=requirement_selection(requirement_ids=(requirement_id,)),
    )
    conn.execute(
        "UPDATE deployment_run_items SET requirement_snapshot=%s "
        "WHERE run_id=%s AND item_id=%s",
        (snapshot, RUN, member),
    )
    conn.commit()


def _seed(conn, carriers):
    plan_id = _plan(conn)
    stages = _stages(plan_id)
    stages[1].pop("cases")
    _seed_run(conn, run_id=RUN, stages=stages, members=MEMBERS)
    for member in carriers:
        _admit_plan_requirement(conn, member, plan_id)
    return plan_id


def _materialize(conn, member):
    return materialize_deployment_qa_stage(
        conn,
        deployment_run_id=RUN,
        deployment_stage="item-qa",
        deployment_member_item_id=member,
    )


def _plan_rows(conn, plan_id):
    return conn.execute(
        "SELECT deployment_member_item_id FROM qa_requirements "
        "WHERE deployment_run_id=%s AND plan_id=%s ORDER BY id",
        (RUN, plan_id),
    ).fetchall()


def test_members_admitting_the_same_plan_form_one_shared_group(test_db):
    plan_id = _seed(test_db, MEMBERS)
    first = _materialize(test_db, MEMBERS[0])
    assert len(first["created_requirement_ids"]) == 1
    for member in MEMBERS[1:]:
        later = _materialize(test_db, member)
        assert later["created_requirement_ids"] == []
        assert later["existing_requirement_ids"] == first["created_requirement_ids"]
    assert [
        row["deployment_member_item_id"] for row in _plan_rows(test_db, plan_id)
    ] == [None]


def test_a_plan_only_one_member_admits_stays_its_private_copy(test_db):
    carrier = MEMBERS[0]
    plan_id = _seed(test_db, (carrier,))
    assert len(_materialize(test_db, carrier)["created_requirement_ids"]) == 1
    assert [
        row["deployment_member_item_id"] for row in _plan_rows(test_db, plan_id)
    ] == [carrier]
