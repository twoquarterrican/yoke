"""A remote hook persists session facts before it responds; telemetry follows.

Wakes and liveness read the registration and turn posture, so they must be
durable by the time the client has its answer. The telemetry rows are
disposable and are written by the flush the route schedules after responding.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from yoke_core.hooks import runner as runner_module
from yoke_core.hooks.remote_entry import evaluate_remote
from yoke_core.hooks.types import HookDecision, Next, Outcome

pytestmark = pytest.mark.usefixtures("bound_project_context")


def test_registration_persists_before_response_and_telemetry_after(
    monkeypatch,
) -> None:
    writes: list[tuple[str, object]] = []
    module = types.ModuleType("remote_hook_order.noop")
    module.evaluate = lambda _context: HookDecision(
        outcome=Outcome.NOOP, next=Next.CONTINUE
    )
    monkeypatch.setitem(sys.modules, "remote_hook_order.noop", module)
    monkeypatch.setattr(
        runner_module, "chain_for", lambda *a, **_k: ["remote_hook_order.noop"]
    )
    monkeypatch.setattr(
        runner_module._telemetry,
        "flush_hook_telemetry",
        lambda records, **kwargs: writes.append(("flush", (list(records), kwargs))),
    )
    monkeypatch.setattr(
        "yoke_core.hooks.session_turn_posture_tail.persist_accepted_hook_turn_posture",
        lambda **kwargs: writes.append(("turn_posture", kwargs["session_id"])),
    )
    monkeypatch.setattr(
        "yoke_core.hooks.remote_lifecycle.run_remote_session_lifecycle",
        lambda *_a: writes.append(("lifecycle", None)),
    )
    stdin = json.dumps(
        {
            "session_id": "s-order",
            "tool_name": "Bash",
            "tool_input": {"command": "true"},
        }
    )

    result = evaluate_remote(
        "PreToolUse",
        stdin,
        "claude",
        None,
        2000,
        project_id=7,
        project_slug="example",
        actor_id=3,
    )

    # Everything the route will respond after: registration, posture, lifecycle.
    assert [kind for kind, _ in writes] == ["flush", "turn_posture", "lifecycle"]
    records, kwargs = writes[0][1]
    assert records == []
    assert kwargs["ensure_session"][0] == "s-order"

    result.flush_telemetry(321)

    kind, (records, kwargs) = writes[-1]
    assert kind == "flush"
    assert "ensure_session" not in kwargs
    dispatch = [fields for record, fields in records if record == "dispatch"]
    assert len(dispatch) == 1
    assert dispatch[0]["extra"]["server_wall_ms"] == 321
