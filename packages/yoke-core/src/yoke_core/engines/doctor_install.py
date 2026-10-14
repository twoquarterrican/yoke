"""Install readiness roster and machine-local observations."""

from __future__ import annotations

import json
import shlex
import os
import urllib.request

from yoke_contracts.engine_version import ENGINE_VERSION_HEADER, local_handshake_version
from yoke_contracts.execution_provenance import collect_execution_provenance
from yoke_contracts.harness_cli_manifest import HARNESS_CLI_MANIFESTS
from yoke_contracts.runtime_identity import SERVED_BUILD_PATH
from yoke_cli.config import universe_ui_daemon_state
from yoke_cli.config.path_harness_clis import resolve_harness_clis
from yoke_cli.transport.dispatcher import build_actor
from yoke_core.domain.control_plane_transport import relay
from yoke_core.domain.project_scratch_dir import scratch_project
from yoke_core.domain.session_orientation_delivery import orientation_delivered
from yoke_core.engines.doctor_registry_types import HealthCheck
from yoke_core.engines.doctor_report import DoctorArgs, RecordCollector, _run

# Guidance checks are kept with their filesystem evidence owner.
from yoke_core.engines.doctor_install_guidance import (
    hc_install_residue,
    hc_installed_guidance,
    hc_instruction_discovery,
)


INSTALL_SLUGS = (
    "machine-registry",
    "session-relay",
    "hook-resident",
    "harness-unattended-posture",
    "project-gh-auth",
    "harness-cli-auth",
    "dashboard-current-build",
    "session-hook-registration",
    "install-residue",
    "installed-guidance",
    "instruction-discovery",
)


def hc_harness_cli_auth(conn, args: DoctorArgs, rec: RecordCollector) -> None:
    found = False
    available = {
        entry.harness_id: entry.path
        for entry in resolve_harness_clis(os.environ.get("PATH"))
    }
    for manifest in HARNESS_CLI_MANIFESTS:
        executable = available.get(manifest.harness_id)
        if executable is None:
            continue
        found = True
        probe = _run([executable, *manifest.auth_args], timeout=5)
        signed_in = probe.returncode == 0
        if manifest.auth_signed_in_key:
            try:
                document = json.loads(probe.stdout)
                signed_in = (
                    signed_in and document.get(manifest.auth_signed_in_key) is True
                )
            except (ValueError, AttributeError):
                signed_in = False
        # Native auth documents contain private account data. Keep only the verdict.
        login = shlex.join((manifest.executable, *manifest.login_args))
        rec.record(
            "harness-cli-auth",
            "Harness CLI sign-in",
            "PASS" if signed_in else "FAIL",
            f"{manifest.executable} is signed in."
            if signed_in
            else f"HARNESS_AUTH_UNVERIFIED: {manifest.executable} sign-in could not be verified. Run `{login}`.",
        )
    if not found:
        rec.record(
            "harness-cli-auth",
            "Harness CLI sign-in",
            "FAIL",
            "HARNESS_CLI_MISSING: no supported harness CLI is installed. Install a harness CLI, sign in, and rerun Doctor.",
        )


def dashboard_identity() -> tuple[str, str]:
    record = universe_ui_daemon_state.read_record()
    if record is None or not universe_ui_daemon_state.process_alive(record.pid):
        raise ValueError("DASHBOARD_NOT_RUNNING")
    host = "127.0.0.1" if record.host in {"0.0.0.0", "::"} else record.host
    if ":" in host:
        host = f"[{host}]"
    with urllib.request.urlopen(
        f"http://{host}:{record.port}{SERVED_BUILD_PATH}", timeout=3
    ) as response:
        return response.read(256).decode("utf-8").strip(), response.headers.get(
            ENGINE_VERSION_HEADER, ""
        )


def hc_dashboard_current_build(conn, args: DoctorArgs, rec: RecordCollector) -> None:
    try:
        build, version = dashboard_identity()
        expected = collect_execution_provenance()["source_sha"]
        installed = local_handshake_version()
        if expected != "unknown":
            current = bool(expected) and build == expected
        else:
            current = bool(installed and installed != "0.1.0") and version == installed
        if not current:
            raise ValueError("DASHBOARD_BUILD_UNVERIFIED")
    except (OSError, ValueError, UnicodeError):
        rec.record(
            "dashboard-current-build",
            "Dashboard runs the installed build",
            "FAIL",
            "DASHBOARD_BUILD_UNVERIFIED: the dashboard is stopped, stale, or has no matching build identity. Run `yoke ui down`, then `yoke ui up`.",
        )
        return
    rec.record(
        "dashboard-current-build",
        "Dashboard runs the installed build",
        "PASS",
        "The running dashboard matches the installed code identity.",
    )


def hc_session_hook_registration(conn, args: DoctorArgs, rec: RecordCollector) -> None:
    try:
        session_id = build_actor().session_id
        if not session_id:
            raise ValueError("SESSION_HOOK_UNOBSERVED")
        identity = relay("sessions.identity", {})
        if identity.get("session_id") != session_id:
            raise ValueError("SESSION_REGISTRATION_UNVERIFIED")
        with scratch_project(str(identity.get("project_id") or args.project or "")):
            if not orientation_delivered(session_id):
                raise ValueError("SESSION_HOOK_UNOBSERVED")
    except Exception:  # identity refusal is a failed observation, not guessed success
        rec.record(
            "session-hook-registration",
            "This session received a registering hook",
            "FAIL",
            "SESSION_HOOK_UNOBSERVED: registration and hook delivery for this session are not both proven. Start a new harness session in the installed project and rerun `yoke doctor run --install`.",
        )
        return
    rec.record(
        "session-hook-registration",
        "This session received a registering hook",
        "PASS",
        "The control plane registered this session and its local hook confirmed orientation delivery.",
    )


INSTALL_HEALTH_CHECKS = [
    HealthCheck("harness-cli-auth", "Harness CLI sign-in", hc_harness_cli_auth),
    HealthCheck(
        "dashboard-current-build",
        "Dashboard runs the installed build",
        hc_dashboard_current_build,
    ),
    HealthCheck(
        "session-hook-registration",
        "This session received a registering hook",
        hc_session_hook_registration,
    ),
    HealthCheck(
        "install-residue", "No configuration from another install", hc_install_residue
    ),
    HealthCheck(
        "installed-guidance",
        "Installed guidance matches the running code",
        hc_installed_guidance,
    ),
    HealthCheck(
        "instruction-discovery",
        "Canonical instructions are reachable",
        hc_instruction_discovery,
    ),
]
