"""Saved project decisions and fresh machine observations stay separate."""

from uuid import uuid4

import pytest

from runtime.api.domain.test_project_onboarding_runs import _conn
from yoke_core.domain import project_onboarding_runs as runs


def _rows(payload):
    return {row["row_id"]: row for row in payload["rows"]}


def test_second_machine_reuses_profile_without_copying_first_machine_checks():
    first_machine, second_machine = str(uuid4()), str(uuid4())
    profile = {"hosting": "deferred", "delivery": "no-default", "testing": "attested-no-tests"}
    with _conn() as conn:
        first = runs.init_run(
            conn=conn, project_id=7, machine_id=first_machine,
            checkout_path="/first", metadata={"execution_profile": profile},
            row_status={"machine-profile": "verified", "hosting-setup": "deferred"},
            evidence={"machine-profile": {"source": "first-machine-check"}},
            observations={"machine-profile": {"status": "verified", "evidence": {"source": "fresh-check"}}},
        )
        second = runs.init_run(
            conn=conn, project_id=7, machine_id=second_machine, checkout_path="/second",
        )
        assert second["run_id"] == first["run_id"]
        assert second["execution_profile"] == profile
        assert second["profile_changed"] is False
        assert _rows(second)["machine-profile"]["status"] == "unknown"
        assert _rows(second)["machine-profile"]["saved_status"] == "unknown"
        assert _rows(second)["hosting-setup"]["saved_status"] == "deferred"
        stored = second["metadata"]["machines"]
        assert stored[first_machine]["checkout_path"] == "/first"
        assert stored[second_machine]["checkout_path"] == "/second"
        assert stored[first_machine]["rows"]["machine-profile"]["status"] == "verified"
        assert second["setup_readiness"]["ready"] is False


def test_read_without_fresh_observations_never_promotes_saved_machine_verification():
    machine = str(uuid4())
    with _conn() as conn:
        first = runs.init_run(
            conn=conn, project_id=7, machine_id=machine,
            row_status={"machine-profile": "verified"},
        )
        read = runs.get_run(first["run_id"], conn=conn, machine_id=machine)
        assert _rows(read)["machine-profile"]["saved_status"] == "verified"
        assert _rows(read)["machine-profile"]["status"] == "unknown"
        assert _rows(read)["machine-profile"]["reason"] == "machine_not_checked"
        assert read["updated_at"] == first["updated_at"]


def test_invalid_machine_or_row_update_leaves_saved_choices_unchanged():
    machine = str(uuid4())
    with _conn() as conn:
        first = runs.init_run(
            conn=conn, project_id=7, machine_id=machine,
            metadata={"execution_profile": {"hosting": "deferred"}},
        )
        for payload in (
            {"machine_id": "not-a-machine", "row_status": {"machine-profile": "verified"}},
            {"row_status": {"strategy-setup": "verified", "unknown-row": "configured"}},
            {"metadata": {"execution_profile": []}},
            {"machine_id": machine, "observations": {"machine-profile": {"status": "verified", "evidence": []}}},
            {"machine_id": machine, "observations": {"machine-profile": {"status": "verified", "recovery": 1}}},
        ):
            with pytest.raises(runs.ProjectOnboardingRunError):
                runs.update_run(conn=conn, run_id=first["run_id"], project_id=7, **payload)
        saved = runs.get_run(first["run_id"], conn=conn, machine_id=machine)
        assert saved["execution_profile"] == first["execution_profile"]
        assert saved["updated_at"] == first["updated_at"]
        assert _rows(saved)["strategy-setup"]["saved_status"] == "unknown"


def test_unknown_optional_capabilities_do_not_become_a_whole_profile_interview():
    with _conn() as conn:
        result = runs.init_run(conn=conn, project_id=7)
        rows = _rows(result)
        assert rows["capability-setup"]["status"] == "unknown"
        assert "capability-setup" not in result["setup_readiness"]["unmet_rows"]


@pytest.mark.parametrize("choice", ["not-needed", "deferred"])
def test_saved_choice_cannot_hide_a_missing_required_connection(choice):
    machine = str(uuid4())
    with _conn() as conn:
        result = runs.init_run(
            conn=conn, machine_id=machine, project_id=7,
            row_status={"yoke-connection": choice},
            observations={"yoke-connection": {"status": "unknown"}},
        )
        assert _rows(result)["yoke-connection"]["saved_status"] == choice
        assert _rows(result)["yoke-connection"]["status"] == "unknown"
        assert "yoke-connection" in result["setup_readiness"]["unmet_rows"]


@pytest.mark.parametrize("rows", [[], [{"row_id": "package-install", "status": "configured"}]])
def test_missing_required_rows_cannot_fabricate_readiness(rows):
    from yoke_core.domain.project_onboarding_facts import project_rows

    _, readiness = project_rows(
        rows, {}, machine_id=None, observations={}, facts={},
        project_id=7, project_access=False,
    )
    assert readiness["ready"] is False
    assert "project-identity" in readiness["unmet_rows"]
    assert "yoke-connection" in readiness["unmet_rows"]


def test_incomplete_saved_checklist_refuses_and_init_restores_only_missing_rows():
    with _conn() as conn:
        first = runs.init_run(conn=conn, project_id=7, row_status={"hosting-setup": "deferred"})
        conn.execute("DELETE FROM project_onboarding_checklist_rows WHERE run_id = %s AND row_id = %s", (first["run_id"], "project-identity"))
        conn.commit()
        with pytest.raises(runs.ProjectOnboardingRunError, match="setup_checklist_incomplete"):
            runs.get_run(first["run_id"], conn=conn)
        resumed = runs.init_run(conn=conn, project_id=7, run_id=first["run_id"])
        assert _rows(resumed)["hosting-setup"]["saved_status"] == "deferred"
        assert resumed["setup_readiness"]["ready"] is False
