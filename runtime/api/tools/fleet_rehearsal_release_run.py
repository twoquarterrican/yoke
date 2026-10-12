"""Name the release run whose control-plane database replays the release driver.

Only the release control plane records and drives releases, so only the
database holding the run being released can replay one; every other tenant
database is rehearsed without that replay. The run is read on the control
plane the receipt is recorded on, and a database holds it when it stores that
run id with that exact creation instant: run ids are allocated per universe, so
an id alone could match an unrelated universe's own run.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Tuple

_READ_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class ReleaseRun:
    """The run being released, as its release control plane records it."""

    run_id: str
    created_at: str
    control_plane: str


def read_release_run(run_id: str, receipt_env: str) -> Tuple[ReleaseRun | None, str]:
    """The named run from the *receipt_env* control plane, or why it is unknown."""
    run_id = run_id.strip()
    if not run_id:
        return None, ""
    if not receipt_env:
        return None, (
            f"--release-run {run_id} is read on the release control plane, and "
            "no control plane is named. Name it with --receipt-env "
            "<control-plane> (`yoke env list`) and retry."
        )
    reason = ""
    try:
        result = subprocess.run(
            ["yoke", "deployment-runs", "get", run_id, "created_at", "--json"],
            capture_output=True,
            text=True,
            timeout=_READ_TIMEOUT_SECONDS,
            env=dict(os.environ, YOKE_ENV=receipt_env),
        )
        envelope = json.loads(result.stdout or "{}")
        created_at = str((envelope.get("result") or {}).get("value") or "").strip()
        if result.returncode == 0 and created_at:
            return ReleaseRun(run_id, created_at, receipt_env), ""
        error = envelope.get("error") or {}
        reason = str(error.get("message") or result.stderr or "no created_at")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        reason = f"{type(exc).__name__}: {exc}"
    return None, (
        f"release_run_unreadable: release run {run_id} could not be read on the "
        f"{receipt_env} control plane ({reason.strip()}). Name the run the "
        "release dispatches, as recorded on the control plane --receipt-env "
        f"names (`yoke --env {receipt_env} deployment-runs list --project "
        "<project>`), and retry."
    )


def unnamed_release_run_refusal(project: str, environment: str) -> str:
    """Why a receipt for a release-replaying fleet needs its release run named."""
    return (
        "release_run_required: this fleet replays the release driver on the "
        "release control plane's database, which is the one holding the run "
        "being released, so a receipt needs that run. Retry: yoke watch "
        f"preflight -- --project {project} {environment} --record-receipt "
        "--product-sha <sha> --receipt-env <control-plane> --release-run <run-id>"
    )


__all__ = ["ReleaseRun", "read_release_run", "unnamed_release_run_refusal"]
