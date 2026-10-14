"""Linux reset carries verified live sign-ins forward and never rolls a newer one back."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest

from yoke_harness.baseline_probe_failure_causes import PROBE_EXIT_CODES
from yoke_harness.ssh_linux_baseline import _ARCHIVE_PROGRAM, archive_operation
from yoke_harness.ssh_linux_reset_preconditions import reset_preflight
from yoke_harness.ssh_linux_sign_in_stores import (
    SIGN_IN_NEWER_THAN_BASELINE,
    SIGN_IN_STORES,
)
from yoke_harness.standard_baseline_probes import (
    SAVE_BASELINE_COMMAND,
    standard_probes,
)

SEALED_PROBES = standard_probes("linux")
CLAUDE, CODEX, CURSOR = SIGN_IN_STORES.values()
SIGNED_OUT = PROBE_EXIT_CODES["probe_harness_exit_nonzero"]


def sealed_host(home: Path, signed_in: set[str]) -> SimpleNamespace:
    """A Linux host whose sealed probes pass only for *signed_in* harnesses.

    The archive command runs the real program against the pytest home, without
    the remote-only writer stop that would reach this machine's daemons.
    """
    probes = {tuple(probe["argv"]): probe["name"] for probe in SEALED_PROBES}
    host = SimpleNamespace(home=str(home), probed=[], archive_runs=0)

    def run_command(argv, timeout=None):
        name = probes[tuple(argv)]
        host.probed.append(name)
        return subprocess.CompletedProcess(
            argv, 0 if name in signed_in else SIGNED_OUT, "", ""
        )

    def run_archive(command, input_text=None, timeout=None):
        host.archive_runs += 1
        arguments = shlex.split(command)[3:]
        # This is the fake remote's interpreter; it only owns pytest's temp home.
        return subprocess.run(
            [sys.executable, "-c", _ARCHIVE_PROGRAM, *arguments],
            input=input_text,
            text=True,
            capture_output=True,
            env={**os.environ, "HOME": str(home)},
            check=False,
        )

    host.run_command = run_command
    host._run = run_archive
    host.read_remote_text = lambda _path: json.dumps({"probes": SEALED_PROBES})
    return host


def test_preflight_verifies_each_sealed_sign_in_by_its_standard_name():
    # Standard probes run through python3; matching by executable name never
    # found Claude, so every reset restored the golden's rotated credential.
    host = sealed_host(Path("/home/tester"), {"Claude real request"})
    plan = reset_preflight(host, "/golden").evidence["sign_in_plan"]
    assert plan["carry"] == [CLAUDE]
    assert set(plan["unverified"]) == {CODEX, CURSOR}
    assert plan["unverified"][CODEX]["probe"] == "Codex real request"
    assert host.probed == list(SIGN_IN_STORES)


@pytest.fixture
def signed_in_home(tmp_path):
    if os.getuid() == 0:
        pytest.skip("archive requires the non-root test user")
    home, golden = tmp_path / "home", tmp_path / "golden"
    for relative in (CLAUDE, CODEX, CURSOR):
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("sealed " + relative)
        path.chmod(0o600)
    (home / CURSOR).chmod(0o644)
    (home / "settings").write_text("golden")
    captured = subprocess.run(
        [sys.executable, "-c", _ARCHIVE_PROGRAM, "capture", str(home), str(golden)],
        input="[]",
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(home)},
    )
    assert captured.returncode == 0, captured.stdout + captured.stderr
    sealed_at = (golden / "manifest.json").stat().st_mtime
    for relative in (CLAUDE, CODEX, CURSOR):
        # The operator signed in again after the seal.
        (home / relative).write_text("live " + relative)
        os.utime(home / relative, (sealed_at + 60, sealed_at + 60))
    (home / "settings").write_text("live")
    return home, golden


def test_sign_in_then_reset_keeps_every_verified_sign_in(signed_in_home):
    home, golden = signed_in_home
    host = sealed_host(home, set(SIGN_IN_STORES))
    for _ in range(2):
        result = archive_operation(host, "reset", str(golden))
        assert result.ok, result.evidence
        assert "ok" not in result.evidence
    for relative in (CLAUDE, CODEX, CURSOR):
        assert (home / relative).read_text() == "live " + relative
        assert relative in result.evidence["preserved_entries"]
    assert (home / CURSOR).stat().st_mode & 0o777 == 0o644
    assert (home / CLAUDE).stat().st_mode & 0o777 == 0o600
    assert (home / "settings").read_text() == "golden"


def test_newer_unverified_sign_in_refuses_before_clearing(signed_in_home):
    home, golden = signed_in_home
    host = sealed_host(home, {"Claude real request", "Cursor real request"})
    result = archive_operation(host, "reset", str(golden))
    assert not result.ok and result.error_code == SIGN_IN_NEWER_THAN_BASELINE
    assert result.evidence["refused_entry"] == CODEX
    assert result.evidence["probe"] == "Codex real request"
    assert SAVE_BASELINE_COMMAND in result.evidence["recovery"]
    assert (home / "settings").read_text() == "live"
    assert (home / CODEX).read_text() == "live " + CODEX


def test_unverified_sign_in_unchanged_since_the_seal_restores_the_golden(
    signed_in_home,
):
    home, golden = signed_in_home
    sealed_at = (golden / "manifest.json").stat().st_mtime
    os.utime(home / CODEX, (sealed_at - 60, sealed_at - 60))
    host = sealed_host(home, {"Claude real request", "Cursor real request"})
    result = archive_operation(host, "reset", str(golden))
    assert result.ok, result.evidence
    assert (home / CODEX).read_text() == "sealed " + CODEX
    assert (home / CLAUDE).read_text() == "live " + CLAUDE
    assert CODEX not in result.evidence["preserved_entries"]


def test_symlinked_sign_in_refuses_before_clearing(signed_in_home):
    home, golden = signed_in_home
    outside = home.parent / "outside"
    (home / CLAUDE).rename(outside)
    (home / CLAUDE).symlink_to(outside)
    host = sealed_host(home, set(SIGN_IN_STORES))
    result = archive_operation(host, "reset", str(golden))
    assert host.archive_runs == 1
    assert not result.ok and result.error_code == "linux_sign_in_store_unsafe"
    assert (home / "settings").read_text() == "live"
