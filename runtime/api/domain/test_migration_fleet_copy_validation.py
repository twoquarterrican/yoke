"""Boundary failures cannot earn convergence proof or leak copy credentials."""

from pathlib import Path
from types import SimpleNamespace

from yoke_core.domain import db_backend, migration_fleet_copy_validation as validation
from yoke_core.domain import postgres_cluster
from yoke_core.domain.migration_fleet_preflight import RehearsalPlan


def test_copy_failure_names_boundary_and_redacts_password():
    def crash(conn, dsn):
        raise ValueError("invalid_instant password=swordfish")

    detail = validation.validate_copy(crash, None, "host=localhost password=swordfish")
    assert "rehearsal_post_boot_failed" in detail
    assert "invalid_instant" in detail
    assert "swordfish" not in detail
    assert "rerun fleet preflight" in detail


def _open_copy(monkeypatch, calls):
    conn = SimpleNamespace(
        rollback=lambda: calls.append("rollback"),
        commit=lambda: calls.append("commit"),
        close=lambda: calls.append("close"),
    )
    monkeypatch.setattr(postgres_cluster, "dsn", lambda *_: "host=copy")
    monkeypatch.setattr(db_backend, "_open_native_postgres", lambda *_: conn)


def test_readers_follow_convergence(monkeypatch):
    calls = []
    _open_copy(monkeypatch, calls)
    pending = ["history"]

    def converge(*_):
        calls.append("converge")
        pending.clear()

    plan = RehearsalPlan(
        ("history",),
        lambda *_: tuple(pending),
        converge,
        post_converge_validator=lambda *_: calls.append("readers"),
    )
    result = validation.converge_copy(
        None, "source", "copy", Path("/tmp/restore.dump"), plan
    )
    assert result.passed
    assert calls == ["converge", "readers", "commit", "close"]
    assert result.pending_before == ("history",)
    assert result.applied == ("history",)


def test_failed_readers_fail_the_copy_without_committing(monkeypatch):
    calls = []
    _open_copy(monkeypatch, calls)
    plan = RehearsalPlan(
        ("history",),
        lambda *_: (),
        lambda *_: calls.append("converge"),
        post_converge_validator=lambda *_: "text >= timestamptz",
    )
    result = validation.converge_copy(
        None, "source", "copy", Path("/tmp/restore.dump"), plan
    )
    assert not result.passed
    assert "rehearsal_post_boot_failed" in result.detail
    assert calls == ["converge", "rollback", "close"]
