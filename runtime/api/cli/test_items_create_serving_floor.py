"""Old serving create contracts never receive a real spec-bearing write."""

import pytest

from yoke_cli.commands.adapters import items_create_dispatch as adapter
from yoke_contracts.api.function_call import (
    FunctionCallResponse,
    FunctionError,
    TargetRef,
)


def response(*, accepted=None, error=None):
    return FunctionCallResponse(
        function="items.create",
        version="v1",
        request_id="test-create-proof",
        success=error is None,
        result={} if accepted is None else {"spec_accepted": accepted},
        error=error,
    )


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize(
    "reply",
    [
        response(),
        response(accepted=False),
        response(
            error=FunctionError(
                code="create_failed",
                message="task item creation requires a nonblank instruction",
            )
        ),
    ],
)
def test_missing_acceptance_refuses_without_write(monkeypatch, capsys, preview, reply):
    calls = []
    writes = []
    monkeypatch.setattr(adapter._helpers, "ensure_handlers_loaded", lambda: None)
    monkeypatch.setattr(
        adapter, "call_dispatcher", lambda **kw: calls.append(kw) or reply
    )
    monkeypatch.setattr(
        adapter._helpers, "dispatch_and_emit", lambda **kw: writes.append(kw) or 0
    )
    assert (
        adapter.dispatch_create(
            target=TargetRef(kind="global"),
            payload={
                "title": "Outcome",
                "workflow": "issue",
                "spec": "Do it.",
                "dry_run": preview,
            },
            session_id=None,
            json_mode=True,
        )
        != 0
    )
    assert len(calls) == 1 and calls[0]["payload"]["dry_run"] is True
    assert not writes
    output = capsys.readouterr().out
    assert "function_argument_version_skew" in output
    assert "next-release" in output and "No item was filed" in output


def test_accepted_contract_is_followed_by_exact_write(monkeypatch):
    probes = []
    writes = []
    monkeypatch.setattr(adapter._helpers, "ensure_handlers_loaded", lambda: None)
    monkeypatch.setattr(
        adapter,
        "call_dispatcher",
        lambda **kw: probes.append(kw) or response(accepted=True),
    )
    monkeypatch.setattr(
        adapter._helpers, "dispatch_and_emit", lambda **kw: writes.append(kw) or 0
    )
    payload = {
        "title": "Outcome",
        "workflow": "issue",
        "spec": "Do it.\n",
        "dry_run": False,
    }
    assert (
        adapter.dispatch_create(
            target=TargetRef(kind="global"),
            payload=payload,
            session_id=None,
            json_mode=False,
        )
        == 0
    )
    assert probes[0]["payload"] == {**payload, "dry_run": True}
    assert writes[0]["payload"] == payload


def test_validation_failure_is_not_reclassified(monkeypatch, capsys):
    error = FunctionError(code="create_failed", message="Title exceeds project limit")
    monkeypatch.setattr(adapter._helpers, "ensure_handlers_loaded", lambda: None)
    monkeypatch.setattr(adapter, "call_dispatcher", lambda **kw: response(error=error))
    assert (
        adapter.dispatch_create(
            target=TargetRef(kind="global"),
            payload={"spec": "Do it."},
            session_id=None,
            json_mode=True,
        )
        != 0
    )
    assert "Title exceeds project limit" in capsys.readouterr().out


def test_contract_change_after_preview_reports_identifiers_and_repair(
    monkeypatch, capsys
):
    monkeypatch.setattr(adapter._helpers, "ensure_handlers_loaded", lambda: None)
    monkeypatch.setattr(
        adapter, "call_dispatcher", lambda **kw: response(accepted=True)
    )
    reference = "-".join(("ACM", "7"))
    written = response().model_copy(update={"result": {"public_ref": reference}})

    def emit_write(**kwargs):
        checked = kwargs["response_recovery"](written, None)
        return adapter._helpers.emit_response(checked, json_mode=True)

    monkeypatch.setattr(adapter._helpers, "dispatch_and_emit", emit_write)
    assert (
        adapter.dispatch_create(
            target=TargetRef(kind="global"),
            payload={"spec": "Do it."},
            session_id=None,
            json_mode=True,
        )
        != 0
    )
    output = capsys.readouterr().out
    assert reference in output and "Do not repeat create" in output
    assert "--field spec --stdin" in output
    assert "No item was filed" not in output
