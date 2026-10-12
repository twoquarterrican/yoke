"""Keep this machine's installed CLI on the release prod serves.

The prod relay re-execs into every release it observes prod serving, so its
start is the event that says "prod now serves this release". There it compares
the operator's installed CLI with the release it runs and, when the CLI is
behind, runs the official installer for exactly that release from the
machine's recorded distribution origin — the relay's own code, so even a CLI
too old to know `yoke update --version` is moved. Nothing runs on a schedule. Every outcome is written to the relay log and to
``operator-cli-follow.json`` in the relay state directory; a CLI left behind
also warns on each command it relays to prod, naming the same recovery.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from yoke_cli.config import self_update
from yoke_cli.config.path_state_contract import tool_bin_dir
from yoke_cli.transport.installed_cli_staleness import update_recovery
from yoke_contracts.engine_version import compare_engine_versions
from yoke_contracts.timestamps import iso8601_now

FOLLOW_RECORD_NAME = "operator-cli-follow.json"
PROBE_TIMEOUT_SECONDS = 30

Runner = Callable[..., subprocess.CompletedProcess[str]]


def follow_release(
    release: str,
    state_dir: Path,
    *,
    run: Runner = subprocess.run,
    executable: Path | None = None,
) -> dict[str, Any]:
    """Install *release* as the operator CLI when the installed one is older."""
    target = release.strip().removeprefix("v")
    yoke = executable or Path(tool_bin_dir()) / "yoke"
    record: dict[str, Any] = {"release": target, "cli": str(yoke), "at": iso8601_now()}
    if not yoke.is_file():
        return _finish(record, state_dir, "no_installed_cli")
    before = _version(run, yoke)
    record["before"] = before
    if compare_engine_versions(before, target) != -1:
        return _finish(record, state_dir, "current")
    try:
        self_update.install_release(
            self_update.resolve_target(version=target), str(yoke)
        )
        detail = ""
    except self_update.SelfUpdateError as exc:
        detail = str(exc)
    except Exception as exc:  # noqa: BLE001 - the relay keeps serving; the record names it
        detail = f"{type(exc).__name__}: {exc}"
    record["after"] = _version(run, yoke)
    if record["after"] == target:
        return _finish(record, state_dir, "updated")
    record["error"] = detail or "the installer produced no output"
    record["recovery"] = update_recovery(target)
    return _finish(record, state_dir, "update_failed")


def _version(run: Runner, yoke: Path) -> str:
    try:
        completed = run(
            [str(yoke), "--version"],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _finish(record: dict[str, Any], state_dir: Path, outcome: str) -> dict[str, Any]:
    record["outcome"] = outcome
    if outcome == "updated":
        print(
            f"Installed CLI follows prod release {record['release']}.", file=sys.stderr
        )
    elif outcome == "update_failed":
        print(
            f"OPERATOR-CLI-FOLLOW-FAILED: installed CLI {record.get('before')!r} "
            f"could not be moved to prod release {record['release']}: "
            f"{record['error']}. Recovery: {record['recovery']}.",
            file=sys.stderr,
        )
    try:
        (state_dir / FOLLOW_RECORD_NAME).write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"could not record the CLI follow outcome: {exc}", file=sys.stderr)
    return record


__all__ = ["FOLLOW_RECORD_NAME", "follow_release"]
