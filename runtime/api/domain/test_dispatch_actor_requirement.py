"""The dispatcher gate refuses side-effecting calls that carry no numeric actor.

``dispatch_permission_for_request`` is the in-process dispatcher's one
permission gate. These cases never reach the database: an actor-less call
is decided before any permission lookup.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from yoke_contracts.api.function_call import (
    ActorContext,
    FunctionCallRequest,
    TargetRef,
)
from yoke_core.domain.dispatch_actor_requirement import (
    ACTOR_REQUIRED,
    numeric_actor_id,
)
from yoke_core.domain.yoke_function_permissions import dispatch_permission_for_request
from yoke_core.domain.yoke_function_registry import RegistryEntry


class _Empty(BaseModel):
    pass


def _entry(function_id: str, *, side_effects: bool) -> RegistryEntry:
    return RegistryEntry(
        function_id=function_id,
        handler=lambda _request: None,
        request_model=_Empty,
        response_model=_Empty,
        stability="stable",
        owner_module=__name__,
        target_kinds=("item",),
        side_effects=("db_write",) if side_effects else (),
        emitted_event_names=(),
        guardrails=(),
        adapter_status="live",
    )


def _request(function_id: str, actor_id) -> FunctionCallRequest:
    return FunctionCallRequest(
        function=function_id,
        actor=ActorContext(actor_id=actor_id, session_id="s-1"),
        target=TargetRef(kind="global"),
        payload={},
    )


@pytest.mark.parametrize("actor_id", [None, "", "yoke-core", "env-actor"])
@pytest.mark.parametrize(
    "function_id",
    ["identity.invite.create", "totally.unknown.sideeffecting.op"],
)
def test_side_effecting_call_without_numeric_actor_refuses(function_id, actor_id):
    decision = dispatch_permission_for_request(
        _entry(function_id, side_effects=True), _request(function_id, actor_id)
    )
    assert decision.error is not None
    error = decision.error.error
    assert error.code == ACTOR_REQUIRED
    assert repr(function_id) in error.message
    assert "yoke setup" in error.message
    if actor_id:
        assert repr(actor_id) in error.message


def test_read_only_call_without_actor_passes():
    decision = dispatch_permission_for_request(
        _entry("identity.invite.list", side_effects=False),
        _request("identity.invite.list", None),
    )
    assert decision.error is None


def test_client_local_call_without_actor_passes():
    decision = dispatch_permission_for_request(
        _entry("auth.set.run", side_effects=True), _request("auth.set.run", None)
    )
    assert decision.error is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("", None), (" 7 ", 7), ("12", 12), ("system", None), ("-3", None)],
)
def test_numeric_actor_id(value, expected):
    assert numeric_actor_id(value) == expected
