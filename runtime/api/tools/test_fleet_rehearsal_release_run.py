"""The run being released is read on its control plane and gates the receipt."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

from yoke_core.domain import migration_preflight_receipt_store as receipt_store
from runtime.api.tools import fleet_rehearsal_release_run as release_runs
from runtime.api.tools import migration_fleet_selection
from runtime.api.tools import preflight_fleet_migrations as preflight
from runtime.api.tools.fleet_rehearsal_release_run import ReleaseRun


def _answer(monkeypatch, *, returncode: int, payload: dict) -> list[tuple]:
    calls: list[tuple] = []

    def run(argv: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append((kwargs["env"]["YOKE_ENV"], argv))
        return SimpleNamespace(
            returncode=returncode, stdout=json.dumps(payload), stderr=""
        )

    monkeypatch.setattr(release_runs.subprocess, "run", run)
    return calls


def test_release_run_is_read_on_the_named_control_plane(monkeypatch) -> None:
    calls = _answer(
        monkeypatch,
        returncode=0,
        payload={"result": {"value": "2026-10-12T23:08:55.380656Z"}},
    )
    run, refusal = release_runs.read_release_run("run-20261012-013", "prod")
    assert refusal == ""
    assert run == ReleaseRun("run-20261012-013", "2026-10-12T23:08:55.380656Z", "prod")
    assert calls == [
        (
            "prod",
            [
                "yoke",
                "deployment-runs",
                "get",
                "run-20261012-013",
                "created_at",
                "--json",
            ],
        )
    ]


def test_unreadable_release_run_refuses_by_name(monkeypatch) -> None:
    _answer(
        monkeypatch,
        returncode=1,
        payload={"error": {"message": "deployment run not found"}},
    )
    run, refusal = release_runs.read_release_run("run-x", "prod")
    assert run is None
    assert refusal.startswith("release_run_unreadable: release run run-x")
    assert "deployment run not found" in refusal
    assert "yoke --env prod deployment-runs list" in refusal


def test_unrunnable_read_refuses_by_name(monkeypatch) -> None:
    def unrunnable(*_args: Any, **_kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(cmd="yoke", timeout=120)

    monkeypatch.setattr(release_runs.subprocess, "run", unrunnable)
    run, refusal = release_runs.read_release_run("run-x", "prod")
    assert run is None and "TimeoutExpired" in refusal


def test_release_run_needs_a_control_plane_to_read_it() -> None:
    run, refusal = release_runs.read_release_run("run-x", "")
    assert run is None and "--receipt-env <control-plane>" in refusal


def test_unnamed_release_run_reads_nothing() -> None:
    assert release_runs.read_release_run("", "prod") == (None, "")


def _replaying_target(monkeypatch) -> list[dict]:
    resolved: list[dict] = []
    target = migration_fleet_selection.FleetTarget(
        project="yoke",
        model_name="primary",
        plan=SimpleNamespace(history=("0001_existing",)),
        databases=lambda _dsn_for: ["yoke_tenant_4"],
        schema_shape_digest=lambda: "digest",
        replays_release_driver=True,
    )

    def resolve(*_args: Any, **kwargs: Any):
        resolved.append(kwargs)
        return target, ""

    monkeypatch.setattr(migration_fleet_selection, "resolve", resolve)
    return resolved


def test_engine_fleet_receipt_requires_the_release_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _replaying_target(monkeypatch)
    argv = ["--project", "yoke", "prod", "--record-receipt", "--receipt-env", "prod"]
    assert preflight.main(argv) == 2
    refusal = capsys.readouterr().err
    assert refusal.startswith("release_run_required:")
    assert "--release-run <run-id>" in refusal


def test_named_release_run_binds_the_fleet_plan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    resolved = _replaying_target(monkeypatch)
    _answer(
        monkeypatch,
        returncode=0,
        payload={"result": {"value": "2026-10-12T23:08:55.380656Z"}},
    )
    monkeypatch.setattr(
        receipt_store,
        "read_declared_admin_connection",
        lambda **_kw: ("", "stop after selection"),
    )
    argv = [
        "--project",
        "yoke",
        "prod",
        "--receipt-env",
        "prod",
        "--release-run",
        "run-7",
    ]
    assert preflight.main(argv) == 2
    assert "stop after selection" in capsys.readouterr().err
    assert resolved[0]["release_run"] == ReleaseRun(
        "run-7", "2026-10-12T23:08:55.380656Z", "prod"
    )
