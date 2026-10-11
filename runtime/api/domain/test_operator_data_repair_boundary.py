"""Human authorization, review digest and closed SQL grammar boundaries."""

from unittest.mock import MagicMock, patch

import pytest

from yoke_contracts.api.function_call import (
    ActorContext,
    FunctionCallRequest,
    TargetRef,
)
from yoke_core.domain.handlers.operator_data_repair import handle_repair
from yoke_core.domain.operator_data_repair import (
    RepairPlan,
    review_digest,
    validate_plan,
)
from yoke_core.domain.operator_data_repair_sql import RepairRefusal, validate_sql


@pytest.mark.parametrize(
    "sql",
    [
        "BEGIN; UPDATE documents SET body='x' WHERE id=1; COMMIT",
        "VACUUM documents",
        "TRUNCATE documents",
        "ALTER TABLE documents ADD x text",
        "DO $$ BEGIN DELETE FROM documents; END $$",
        "COPY documents FROM STDIN",
        "UPDATE documents SET body='x'",
        "DELETE FROM documents",
        "WITH removed AS (DELETE FROM others RETURNING *) UPDATE documents SET body='x' WHERE id=1",
        "UPDATE documents SET body='x' FROM others WHERE documents.id=others.id",
        "DELETE FROM documents USING others WHERE documents.id=others.id",
        "UPDATE documents SET body=(SELECT body FROM others) WHERE id=1",
        "UPDATE documents SET body=pg_read_file('/tmp/private') WHERE id=1",
        "UPDATE documents SET body=nextval('sequence')::text WHERE id=1",
        "UPDATE documents SET body=public.replace(body,'x','y') WHERE id=1",
        "UPDATE documents SET body='x'::public.custom_type WHERE id=1",
        "UPDATE documents SET body='x' WHERE id OPERATOR(public.=) 1",
        "UPDATE documents SET id=2 WHERE id=1",
        "UPDATE other SET body='x' WHERE id=1",
        "UPDATE pg_catalog.documents SET body='x' WHERE id=1",
        "UPDATE documents d SET body='x' WHERE id=1",
        "UPDATE documents SET body='x' WHERE id=1 RETURNING *",
    ],
)
def test_nontransactional_unbounded_and_side_effecting_sql_is_refused(sql):
    with pytest.raises(RepairRefusal):
        validate_sql(sql, "documents", ["id"])


def document(**overrides):
    fields = dict(
        sql="UPDATE documents SET body='new' WHERE id=1",
        table="documents",
        key_columns=["id"],
        before=[{"id": 1, "body": "old"}],
        after=[{"id": 1, "body": "new"}],
        reason="Reviewed repair",
    )
    fields.update(overrides)
    return RepairPlan(**fields)


def test_exact_review_digest_covers_sql_rows_and_reason():
    plan = document()
    digest = review_digest(plan)
    validate_plan(plan, digest)
    for changed in (
        document(reason="different"),
        document(sql=plan.sql + " "),
        document(after=[{"id": 1, "body": "other"}]),
    ):
        with pytest.raises(RepairRefusal) as refused:
            validate_plan(changed, digest)
        assert refused.value.code == "repair_review_changed"


@pytest.mark.parametrize(
    "changes",
    [
        {"before": [{"id": 1}], "after": [{"id": 1}]},
        {"after": [{"id": 2, "body": "new"}]},
        {"before": [{"id": 1, "body": "old"}, {"id": 1, "body": "old"}]},
        {"before": [{"id": 1, "body": '{"secret":"private"}'}]},
        {"before": [{"id": None, "body": "old"}]},
    ],
)
def test_incomplete_duplicate_changed_or_sensitive_row_guards_refuse(changes):
    plan = document(**changes)
    with pytest.raises(RepairRefusal):
        validate_plan(plan, review_digest(plan))


def test_semicolons_in_strings_are_not_statement_boundaries():
    stmt = validate_sql(
        "UPDATE documents SET body='x; COMMIT' WHERE id=1 -- harmless comment",
        "documents",
        ["id"],
    )
    assert "RETURNING id" in stmt.mutation
    assert stmt.changed_columns == ("body",)


@pytest.mark.parametrize(
    "actor,session", [("2", "agent"), ("anonymous", ""), ("service", "")]
)
def test_harness_or_anonymous_identity_cannot_repair(actor, session):
    request = FunctionCallRequest(
        function="operator.data_repair.run",
        actor=ActorContext(actor_id=actor, session_id=session),
        target=TargetRef(kind="global"),
        payload={},
    )
    with patch(
        "yoke_core.domain.handlers.operator_data_repair.db_helpers.connect"
    ) as connect:
        outcome = handle_repair(request)
    assert not outcome.primary_success
    assert outcome.error.code == "human_operator_required"
    connect.assert_not_called()


def test_human_identity_still_requires_control_plane_permission():
    from yoke_core.domain.actor_permissions import PermissionDenied

    plan = document()
    request = FunctionCallRequest(
        function="operator.data_repair.run",
        actor=ActorContext(actor_id="2", session_id=""),
        target=TargetRef(kind="global"),
        payload={"plan": plan.model_dump(), "reviewed_sha256": review_digest(plan)},
    )
    with (
        patch(
            "yoke_core.domain.handlers.operator_data_repair.db_helpers.connect",
            return_value=MagicMock(),
        ),
        patch(
            "yoke_core.domain.handlers.operator_data_repair.require_control_plane_permission",
            side_effect=PermissionDenied("no org grant"),
        ),
    ):
        outcome = handle_repair(request)
    assert outcome.error.code == "operator_permission_required"


def test_registration_declares_floor_and_no_claim_or_session_requirement():
    from yoke_core.domain.handlers import _register_operator_data_repair

    registry = MagicMock()
    _register_operator_data_repair.register(registry)
    kwargs = registry.register.call_args.kwargs
    assert kwargs["minimum_serving_version"] == "next-release"
    assert kwargs["claim_required_kind"] is None
    assert kwargs["ambient_session_required"] is False


def test_cli_dispatches_reviewed_document_without_project_or_lane_context(tmp_path):
    import json
    from yoke_cli.commands.adapters.operator_data_repair import operator_data_repair

    plan = document()
    content = tmp_path / "repair.json"
    content.write_text(json.dumps(plan.model_dump()), encoding="utf-8")
    with patch(
        "yoke_cli.commands.adapters.operator_data_repair.dispatch_and_emit",
        return_value=0,
    ) as dispatch:
        assert (
            operator_data_repair(
                [
                    "--content-file",
                    str(content),
                    "--reviewed-sha256",
                    review_digest(plan),
                    "--dry-run",
                ]
            )
            == 0
        )
    call = dispatch.call_args.kwargs
    assert call["target"].kind == "global"
    assert call["session_id"] is None
    assert call["payload"]["dry_run"] is True
    assert call["payload"]["plan"] == plan.model_dump()
