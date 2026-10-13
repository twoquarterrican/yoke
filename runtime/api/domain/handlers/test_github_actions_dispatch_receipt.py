"""Durable receipt reads preserve project authority and original dispatch inputs."""

from types import SimpleNamespace

import pytest
from yoke_contracts.api.function_call import (
    ActorContext,
    FunctionCallRequest,
    TargetRef,
)
from yoke_core.domain.handlers import github_actions_dispatch_receipt as subject
from yoke_core.domain.github_workflow_dispatch_intents import DispatchIntentStoreError


@pytest.fixture
def dispatch_request(monkeypatch):
    monkeypatch.setattr(
        subject,
        "_validate_and_resolve_auth",
        lambda req, model, function_id, **_: (
            model.model_validate(req.payload),
            object(),
            None,
        ),
    )
    return FunctionCallRequest(
        function=subject.FUNCTION_ID,
        actor=ActorContext(actor_id="1", session_id="receipt-test"),
        target=TargetRef(kind="global"),
        payload={"project": "app", "dispatch_request_id": "content-key"},
        options={"authorized_project_id": 7},
    )


def test_original_inputs_and_run_are_read_from_durable_owner(
    dispatch_request, monkeypatch
):
    monkeypatch.setattr(
        subject,
        "latest_intent",
        lambda key: SimpleNamespace(
            authorization_scope="project:7",
            inputs={"product_ref": "a" * 40},
            workflow_run_id="42",
            state="completed",
        ),
    )
    outcome = subject.handle_dispatch_receipt_get(dispatch_request)
    assert outcome.primary_success
    assert outcome.result_payload == {
        "found": True,
        "inputs": {"product_ref": "a" * 40},
        "run_id": "42",
        "state": "completed",
    }


def test_no_receipt_is_distinct_from_unreadable_state(dispatch_request, monkeypatch):
    monkeypatch.setattr(subject, "latest_intent", lambda _: None)
    assert (
        subject.handle_dispatch_receipt_get(dispatch_request).result_payload["found"]
        is False
    )

    def fail(_):
        raise DispatchIntentStoreError("database unavailable")

    monkeypatch.setattr(subject, "latest_intent", fail)
    outcome = subject.handle_dispatch_receipt_get(dispatch_request)
    assert not outcome.primary_success
    assert outcome.error.code == "workflow_dispatch_state_unavailable"
    assert "retry the same request id" in outcome.error.recovery_hint


@pytest.mark.parametrize("authorized", [None, 8])
def test_another_project_cannot_read_original_inputs(
    dispatch_request, monkeypatch, authorized
):
    dispatch_request.options["authorized_project_id"] = authorized
    monkeypatch.setattr(
        subject,
        "latest_intent",
        lambda _: SimpleNamespace(
            authorization_scope="project:7",
            inputs={"private": "hidden"},
        ),
    )
    outcome = subject.handle_dispatch_receipt_get(dispatch_request)
    assert outcome.error.code == "workflow_dispatch_scope_mismatch"
    assert outcome.result_payload == {}


def test_receipt_cli_routes_the_exact_key_and_project(monkeypatch, capsys):
    from yoke_cli.commands.adapters import github_actions_dispatch_receipt as adapter
    from yoke_contracts.api.function_call import FunctionCallResponse
    from yoke_cli.main import main

    seen = []

    def call(function_id, payload, **kwargs):
        seen.append((function_id, payload))
        return FunctionCallResponse(
            success=True, function=function_id, version="v1", result={"found": False}
        )

    monkeypatch.setattr(adapter, "_call", call)
    assert (
        main(
            [
                "github-actions",
                "dispatch-receipt",
                "get",
                "tree-key",
                "--project",
                "app",
                "--json",
            ]
        )
        == 0
    )
    assert seen == [
        (subject.FUNCTION_ID, {"project": "app", "dispatch_request_id": "tree-key"})
    ]
    assert '"found": false' in capsys.readouterr().out


def test_read_works_under_local_bootstrap_authority():
    from yoke_core.domain.github_actions_local_authority import _ALLOWED_FUNCTIONS

    assert subject.FUNCTION_ID in _ALLOWED_FUNCTIONS
