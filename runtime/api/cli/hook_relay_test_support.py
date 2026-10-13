"""Deterministic registered-client context for hook relay protocol tests."""

from types import SimpleNamespace

import pytest
from yoke_cli.transport.https import HttpsConnection

_RESOLVE = "yoke_cli.transport.https.resolve_https_connection"

_HOME_FACT = {"_yoke_client_machine_home": {"schema": 1, "root": "/home"}}


@pytest.fixture(autouse=True)
def local_subset(monkeypatch):
    """Pin the relay's client-side half to a deterministic allow."""
    from yoke_harness.hooks.local_subset import LocalSubsetEvaluation

    holder = SimpleNamespace(
        result=LocalSubsetEvaluation("", 0, False, _HOME_FACT),
        calls=[],
    )

    def fake(
        event_name,
        stdin_data,
        executor,
        agent_type,
        deadline,
        *,
        defer_main_commit=False,
        lint_config_snapshot=None,
    ):
        holder.calls.append(
            (
                event_name,
                executor,
                agent_type,
                defer_main_commit,
                lint_config_snapshot,
            )
        )
        return holder.result

    monkeypatch.setattr(
        "yoke_harness.hooks.relay.evaluate_local_subset",
        fake,
    )
    monkeypatch.setattr(
        "yoke_harness.hooks.relay._client_lint_config_snapshot",
        lambda _payload: {},
    )
    monkeypatch.setattr(
        "yoke_harness.hooks.relay.project_id_for_payload", lambda _payload: 7
    )
    return holder


@pytest.fixture()
def https_connection(monkeypatch):
    connection = HttpsConnection(api_url="https://env.example", token="tok")
    monkeypatch.setattr(_RESOLVE, lambda: connection)
    return connection
