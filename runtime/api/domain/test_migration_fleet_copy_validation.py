"""Boundary failures cannot earn convergence proof or leak copy credentials."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from yoke_core.domain import db_backend, migration_fleet_copy_validation as validation
from yoke_core.domain import postgres_cluster
from yoke_core.domain.migration_fleet_preflight import RehearsalPlan


@pytest.mark.parametrize("boundary", ["pre_boot", "post_boot"])
def test_copy_failure_names_boundary_and_redacts_password(boundary):
    def crash(conn, dsn):
        raise ValueError("invalid_instant password=swordfish")

    detail = validation.validate_copy(
        crash, None, "host=localhost password=swordfish", boundary
    )
    assert f"rehearsal_{boundary}_failed" in detail
    assert "invalid_instant" in detail
    assert "swordfish" not in detail
    assert "rerun fleet preflight" in detail


def test_driver_precedes_convergence_and_readers_follow_it(monkeypatch):
    calls = []
    conn = SimpleNamespace(
        rollback=lambda: calls.append("rollback"),
        commit=lambda: calls.append("commit"),
        close=lambda: calls.append("close"),
    )
    monkeypatch.setattr(postgres_cluster, "dsn", lambda *_: "host=copy")
    monkeypatch.setattr(db_backend, "_open_native_postgres", lambda *_: conn)
    pending = ["history"]

    def converge(*_):
        calls.append("converge")
        pending.clear()

    plan = RehearsalPlan(
        ("history",),
        lambda *_: tuple(pending),
        converge,
        pre_converge_validator=lambda *_: calls.append("driver"),
        post_converge_validator=lambda *_: calls.append("readers"),
    )
    result = validation.converge_copy(
        None, "source", "copy", Path("/tmp/restore.dump"), plan
    )
    assert result.passed
    assert calls == ["driver", "converge", "readers", "commit", "close"]
    assert result.pending_before == ("history",)
    assert result.applied == ("history",)


def test_failed_driver_never_applies_history(monkeypatch):
    calls = []
    conn = SimpleNamespace(
        rollback=lambda: calls.append("rollback"), close=lambda: calls.append("close")
    )
    monkeypatch.setattr(postgres_cluster, "dsn", lambda *_: "host=copy")
    monkeypatch.setattr(db_backend, "_open_native_postgres", lambda *_: conn)
    plan = RehearsalPlan(
        ("history",),
        lambda *_: ("history",),
        lambda *_: pytest.fail("must not converge"),
        pre_converge_validator=lambda *_: "text >= timestamptz",
    )
    result = validation.converge_copy(
        None, "source", "copy", Path("/tmp/restore.dump"), plan
    )
    assert not result.passed
    assert "rehearsal_pre_boot_failed" in result.detail
    assert result.applied == ()
    assert calls == ["rollback", "close"]
