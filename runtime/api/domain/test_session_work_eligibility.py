"""Admission accepts any configured level and ignores launch stamps."""

import pytest
from yoke_contracts.levels import parse_levels
from yoke_core.domain import session_work_eligibility as admission
from yoke_core.domain.sessions_analytics import SessionError
from runtime.api.fixtures.level_store import levels_doc
from runtime.api.fixtures.model_catalog import RECORDS


@pytest.fixture
def configured(monkeypatch):
    levels = parse_levels(
        levels_doc(
            ("INTERN", [{"model": "claude-haiku-5-5", "min_effort": "max"}]),
            ("JUNIOR", [{"model": "grok-4.7", "min_effort": "high"}]),
        )
    )
    monkeypatch.setattr(
        admission, "effective_levels", lambda *args: (levels, "universe")
    )
    monkeypatch.setattr(admission, "current_model_records", lambda conn: RECORDS)


def test_any_matching_configured_level_admits_work(configured):
    assert (
        admission.require_work_selection(
            None,
            project_id=1,
            executor="cursor",
            model="grok-4.7-high-fast",
            reasoning_effort=None,
        )
        == "JUNIOR"
    )


@pytest.mark.parametrize(
    "model,effort", [("unknown", "high"), ("grok-4.7", None), ("grok-4.7", "low")]
)
def test_unknown_or_below_all_options_refuses_with_recovery(configured, model, effort):
    with pytest.raises(SessionError) as refusal:
        admission.require_work_selection(
            None, project_id=1, executor="cursor", model=model, reasoning_effort=effort
        )
    assert refusal.value.code == "SESSION_BELOW_INTERN"
    assert "Recovery:" in str(refusal.value)
