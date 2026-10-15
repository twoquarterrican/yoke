"""Run/stage plan membership shared by one materialization operation."""

import json
from collections import Counter
from collections.abc import Mapping

from yoke_core.domain.db_helpers import query_rows
from yoke_core.domain.qa_execution_environment_target import canonical_target


class MaterializationProjection:
    """Keep selection facts local; never retain requirements or write outcomes."""

    def __init__(self, conn, run_id, stage_name):
        self.conn = conn
        self.run_id = run_id
        self.stage_name = stage_name
        self._members = None
        self._selections = {}
        self._groups = None

    def members(self):
        if self._members is None:
            self._members = query_rows(
                self.conn,
                "SELECT m.item_id,m.requirement_snapshot,i.project_id "
                "FROM deployment_run_items m JOIN items i ON i.id=m.item_id "
                "WHERE m.run_id=%s ORDER BY m.item_id",
                (self.run_id,),
            )
        return self._members

    def shareable(self, subject, target, snapshots):
        from yoke_core.domain.deployment_qa_shared_plans import (
            _formed_group_plan_ids,
            _member_attached_plan_ids,
        )
        from yoke_core.domain.qa_deployment_member_attached_plans import (
            stage_environment_id_for_plan_selection,
        )

        member = subject.get("member_item_id")
        if member is None:
            return []
        environment_id = stage_environment_id_for_plan_selection(self.conn, target)
        key = (environment_id, (target.get("environment") or {}).get("name"))
        if key not in self._selections:
            selected = {}
            for row in self.members():
                raw = row["requirement_snapshot"]
                snapshot = (
                    raw if isinstance(raw, Mapping) else json.loads(str(raw or "{}"))
                )
                selected[int(row["item_id"])] = _member_attached_plan_ids(
                    self.conn, int(row["item_id"]), snapshot, target, environment_id
                )
            counts = Counter(plan for plans in selected.values() for plan in plans)
            formed = _formed_group_plan_ids(self.conn, self.run_id, self.stage_name)
            self._selections[key] = {
                owner: {plan for plan in plans if counts[plan] > 1 or plan in formed}
                for owner, plans in selected.items()
            }
        ids = self._selections[key].get(int(member), set())
        return [
            snapshot for snapshot in snapshots if int(snapshot["plan"]["id"]) in ids
        ]

    def group_members(self, subject, target):
        from yoke_core.domain.deployment_qa_stage_contract import (
            deployment_qa_stage_subject,
        )
        from yoke_core.domain.deployment_qa_execution_target import (
            deployment_qa_execution_target,
        )
        from yoke_core.domain.deployment_qa_shared_plans import member_plan_subjects

        if self._groups is None:
            groups = {}
            for row in self.members():
                member = int(row["item_id"])
                try:
                    selected_subject = deployment_qa_stage_subject(
                        self.conn,
                        run_id=self.run_id,
                        stage_name=self.stage_name,
                        member_item_id=member,
                        require_active=False,
                    )
                    member_target = deployment_qa_execution_target(
                        self.conn, selected_subject
                    )
                    selected = member_plan_subjects(
                        self.conn, selected_subject, member_target, projection=self
                    )
                    for group in selected:
                        # resolve_shared_subject also restricts the plan to the
                        # attaching member's project before comparing targets.
                        if int(group["shared_snapshot"]["plan"]["project_id"]) != int(
                            row["project_id"]
                        ):
                            continue
                        resolved = deployment_qa_execution_target(self.conn, group)
                        groups.setdefault(canonical_target(resolved), []).append(member)
                except ValueError:
                    continue
            self._groups = groups
        return self._groups.get(canonical_target(target), [])
