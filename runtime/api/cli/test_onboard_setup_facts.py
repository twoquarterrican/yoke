"""Local observations and serving-contract refusals use real boundary shapes."""

import json
import pytest
from uuid import uuid4

from yoke_cli.config.onboard_setup_facts import collect
from yoke_cli.commands.adapters import onboard_checklist_get as read_adapter
from yoke_contracts.api.function_call import FunctionCallResponse, TargetRef


def test_missing_identity_stays_unchecked(tmp_path):
    assert collect(config_path=tmp_path / "missing.json", checkout_path=tmp_path) == {
        "machine_id": None, "observations": {},
    }


def test_configuration_changes_are_rechecked_without_exposing_credentials(tmp_path):
    config = tmp_path / "config.json"
    identity = str(uuid4())
    payload = {
        "machine_id": identity, "active_env": "prod",
        "connections": {"prod": {"transport": "https", "api_url": "https://example.invalid",
                                  "credential_source": {"kind": "token_file", "path": str(tmp_path / "token")}}},
    }
    config.write_text(json.dumps(payload))
    first = collect(config_path=config, checkout_path=tmp_path)
    assert first["machine_id"] == identity
    assert first["observations"]["yoke-connection"]["status"] == "configured"
    assert "credential_source" not in json.dumps(first)
    payload["connections"] = {}
    config.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="setup_machine_config_unreadable"):
        collect(config_path=config, checkout_path=tmp_path)


def test_old_schema_refuses_without_sending_a_mutation(monkeypatch):
    calls = []
    monkeypatch.setattr(read_adapter, "ensure_handlers_loaded", lambda: None)
    def dispatch(**kwargs):
        calls.append(kwargs)
        return FunctionCallResponse(version="v1", success=True, function=kwargs["function_id"], result={"schema_version": 1})
    monkeypatch.setattr(read_adapter, "call_dispatcher", dispatch)
    response = read_adapter.get_setup(
        {"project_id": 7, "row_status": {"strategy-setup": "verified"}},
        TargetRef(kind="global", project_id="7"),
    )
    assert response.success is False
    assert response.error.code == "setup_facts_unavailable"
    assert [call["function_id"] for call in calls] == ["onboard.checklist.get"]
    assert "row_status" not in calls[0]["payload"]
