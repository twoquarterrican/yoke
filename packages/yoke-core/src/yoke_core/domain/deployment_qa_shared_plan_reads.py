"""Member plan selection facts reused during Shipping QA presentation."""

import json
from collections.abc import Mapping
from typing import Any

from yoke_core.domain.db_helpers import query_rows
from yoke_core.domain.deployment_qa_presentation_reads import (
    presentation_active,
    presentation_read,
)


def _member_attached_plan_ids(conn, member, snapshot, target, environment_id):
    return presentation_read(
        conn,
        (
            "qa_attached_plans",
            member,
            json.dumps(snapshot, sort_keys=True),
            environment_id,
            str((target.get("environment") or {}).get("name") or ""),
        ),
        lambda: _read_member_attached_plan_ids(
            conn, member, snapshot, target, environment_id
        ),
    )


def _read_member_attached_plan_ids(
    conn: Any,
    member: int,
    snapshot: Mapping | None,
    target: Mapping,
    environment_id: int | None,
) -> set[int]:
    """Plans one member selects for this stage: attached, frozen or admitted."""
    from yoke_core.domain.deployment_qa_frozen_plan_selection import member_requirements
    from yoke_core.domain.qa_deployment_member_attached_plans import (
        attached_member_plan_ids,
    )

    ids = set(
        attached_member_plan_ids(
            conn, member_item_id=member, environment_id=environment_id
        )
    )
    for value in (snapshot or {}).get("plans") or []:
        if (value.get("attachment") or {}).get("qa_phase") == "post_deploy":
            ids.add(int(value["plan"]["id"]))
    admitted = {"member_item_id": member, "member_snapshot": snapshot}
    for requirement in member_requirements(conn, admitted, target=target):
        if requirement.get("plan_id") is not None:
            ids.add(int(requirement["plan_id"]))
    return ids


def _other_members_plan_ids(
    conn: Any, run_id: str, member: int, target: Mapping, environment_id: int | None
) -> set[int]:
    """Plans any other member of the run attached for the same environment."""

    def read():
        batch = presentation_active()
        member_filter = "" if batch else " AND item_id<>%s"
        return {
            int(row["item_id"]): _member_attached_plan_ids(
                conn,
                int(row["item_id"]),
                row["requirement_snapshot"]
                if isinstance(row["requirement_snapshot"], Mapping)
                else json.loads(str(row["requirement_snapshot"] or "{}")),
                target,
                environment_id,
            )
            for row in query_rows(
                conn,
                "SELECT item_id,requirement_snapshot FROM deployment_run_items "
                f"WHERE run_id=%s{member_filter} ORDER BY item_id",
                (run_id,) if batch else (run_id, member),
            )
        }

    plans = presentation_read(
        conn,
        (
            "qa_member_plans",
            run_id,
            environment_id,
            str((target.get("environment") or {}).get("name") or ""),
        ),
        read,
    )
    return set().union(*(ids for other, ids in plans.items() if other != member))


def _formed_group_plan_ids(conn: Any, run_id: str, stage_name: str) -> set[int]:
    return presentation_read(
        conn,
        ("qa_formed_groups", run_id, stage_name),
        lambda: _read_formed_group_plan_ids(conn, run_id, stage_name),
    )


def _read_formed_group_plan_ids(conn: Any, run_id: str, stage_name: str) -> set[int]:
    """Plans whose shared group already holds live memberless rows in this stage."""
    from yoke_core.domain.qa_obligation_settlement import unretracted_requirement_sql

    return {
        int(row["plan_id"])
        for row in query_rows(
            conn,
            "SELECT DISTINCT plan_id FROM qa_requirements "
            "WHERE deployment_run_id=%s AND deployment_stage=%s "
            "AND deployment_member_item_id IS NULL AND plan_id IS NOT NULL "
            f"AND {unretracted_requirement_sql(conn)}",
            (run_id, stage_name),
        )
    }
