"""A bound workflow uses the preparation receipt and refuses incomplete proof."""

from unittest import mock
import pytest
from yoke_contracts.api.function_call import FunctionCallResponse, FunctionError
from yoke_core.domain import deploy_pipeline_bound_inputs as module
from yoke_core.domain.deployment_run_bound_sources import (
    BOUND_SOURCES_PREPARE_FUNCTION_ID,
)

CONFIG = {"input_bindings": {"consumer_sha": {"project": "consumer", "branch": "main"}}}
OLD = "a" * 40
CURRENT = "b" * 40


def _prepare(*, result=None, code="", message=""):
    response = FunctionCallResponse(
        success=not bool(code),
        function=BOUND_SOURCES_PREPARE_FUNCTION_ID,
        version="v1",
        result=result or {},
        error=FunctionError(code=code, message=message) if code else None,
    )
    members = ["YOK-1"]
    with mock.patch.object(module, "call_dispatcher", return_value=response) as call:
        values, reason = module.bound_inputs_for_dispatch(
            CONFIG,
            name="hosted-release",
            run_id="run-test",
            bound_inputs={"consumer_sha": OLD},
            member_items=members,
        )
    assert call.call_args.kwargs["function_id"] == BOUND_SOURCES_PREPARE_FUNCTION_ID
    assert call.call_args.kwargs["payload"] == {"stage_name": "hosted-release"}
    return values, reason, members


def test_refreshed_inputs_and_members_replace_the_drivers_cached_projection():
    values, reason, members = _prepare(
        result={
            "bound_sources": {"inputs": {"consumer_sha": CURRENT}},
            "members": [{"public_ref": "YOK-1"}, {"public_ref": "CON-2"}],
            "rebound": [
                {"project": "consumer", "frozen_sha": OLD, "current_sha": CURRENT}
            ],
        }
    )
    assert values == {"consumer_sha": CURRENT}
    assert reason == ""
    assert members == ["YOK-1", "CON-2"]


@pytest.mark.parametrize(
    "code", ["forbidden", "function_version_skew", "function_not_registered"]
)
def test_unserved_or_refused_preparation_names_authority_recovery(code):
    values, reason, members = _prepare(
        code=code, message="required serving floor next-release"
    )
    assert "was not dispatched" in reason
    assert "required serving floor next-release" in reason
    assert "paired source-dev authority" in reason
    assert values == {"consumer_sha": OLD} and members == ["YOK-1"]


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"bound_sources": {}, "members": []},
        {"bound_sources": {"inputs": {"consumer_sha": ""}}, "members": []},
        {"bound_sources": {"inputs": {"consumer_sha": CURRENT}}, "members": [{}]},
    ],
)
def test_incomplete_preparation_receipts_never_authorize_dispatch(result):
    _values, reason, members = _prepare(result=result)
    assert reason
    assert members == ["YOK-1"]


def test_unbound_stage_needs_no_preparation():
    with mock.patch.object(module, "call_dispatcher") as call:
        assert module.bound_inputs_for_dispatch(
            {}, name="plain", run_id="run-test", bound_inputs={}, member_items=[]
        ) == ({}, "")
    call.assert_not_called()
